from collections import OrderedDict

from models import InheritedMutation, Disease
from models import ClinicalData
from imports.mutations import MutationImporter
from imports.mutations import make_metadata_ordered_dict
from helpers.parsers import parse_tsv_file
from helpers.parsers import gzip_open_text
from database import restart_autoincrement, get_or_create, get_highest_id
from database import bulk_ORM_insert
from database import db


class Importer(MutationImporter):

    model = InheritedMutation
    default_path = 'data/mutations/clinvar_muts_annotated.txt.gz'
    header = [
        'Chr', 'Start', 'End', 'Ref', 'Alt', 'Func.refGene', 'Gene.refGene',
        'GeneDetail.refGene', 'ExonicFunc.refGene', 'AAChange.refGene', 'V11',
        'V12', 'V13', 'V14', 'V15', 'V16', 'V17', 'V18', 'V19', 'V20', 'V21'
    ]
    insert_keys = (
        'mutation_id',
        'db_snp_id',
        'is_low_freq_variation',
        'is_validated',
        'is_in_pubmed_central',
    )

    @staticmethod
    def _beautify_disease_name(name):
        return name.replace('\\x2c', ',').replace('_', ' ')

    def parse(self, path):
        clinvar_mutations = []
        clinvar_data = []
        duplicates = 0
        new_diseases = OrderedDict()

        clinvar_keys = (
            'RS',
            'MUT',
            'VLD',
            'PMC',
            'CLNSIG',
            'CLNDBN',
            'CLNREVSTAT',
        )

        highest_disease_id = get_highest_id(Disease)

        def clinvar_parser(line):
            nonlocal highest_disease_id, duplicates

            metadata = line[20].split(';')

            clinvar_entry = make_metadata_ordered_dict(clinvar_keys, metadata)

            names, statuses, significances = (
                (entry.replace('|', ',').split(',') if entry else None)
                for entry in
                (
                    clinvar_entry[key]
                    for key in ('CLNDBN', 'CLNREVSTAT', 'CLNSIG')
                )
            )

            # those length should be always equal if they exists
            sub_entries_cnt = max(
                [
                    len(x)
                    for x in (names, statuses, significances)
                    if x
                ] or [0]
            )

            at_least_one_significant_sub_entry = False

            for i in range(sub_entries_cnt):

                try:
                    if names:
                        if names[i] not in ('not_specified', 'not provided'):
                            names[i] = self._beautify_disease_name(names[i])
                            at_least_one_significant_sub_entry = True
                    if statuses and statuses[i] == 'no_criteria':
                        statuses[i] = None
                except IndexError:
                    print('Malformed row (wrong count of subentries) on %s-th entry:' % i)
                    print(line)
                    return False

            values = list(clinvar_entry.values())

            # following 2 lines are result of issue #47 - we don't import those
            # clinvar mutations that do not have any diseases specified:
            if not at_least_one_significant_sub_entry:
                return

            for mutation_id in self.preparse_mutations(line):

                duplicated = self.look_after_duplicates(mutation_id, clinvar_mutations, values[:4])
                if duplicated:
                    duplicates += 1
                    continue

                # Python 3.5 makes it easy: **values (but is not available)
                clinvar_mutations.append(
                    (
                        mutation_id,
                        values[0],
                        values[1],
                        values[2],
                        values[3],
                    )
                )

                for i in range(sub_entries_cnt):
                    name = names[i]

                    # we don't won't _uninteresting_ data
                    if name in ('not_specified', 'not provided'):
                        continue

                    if name in new_diseases:
                        disease_id = new_diseases[name]
                    else:
                        disease, created = get_or_create(Disease, name=name)
                        if created:
                            highest_disease_id += 1
                            new_diseases[name] = highest_disease_id
                            disease_id = highest_disease_id
                        else:
                            disease_id = disease.id

                    clinvar_data.append(
                        (
                            len(clinvar_mutations),
                            int(significances[i]) if significances is not None else None,
                            disease_id,
                            statuses[i] if statuses else None,
                        )
                    )

        parse_tsv_file(
            path,
            clinvar_parser,
            self.header,
            file_opener=gzip_open_text
        )

        print('%s duplicates found' % duplicates)

        return clinvar_mutations, clinvar_data, new_diseases.keys()

    def insert_details(self, details):
        clinvar_mutations, clinvar_data, new_diseases = details
        self.insert_list(clinvar_mutations)

        bulk_ORM_insert(
            ClinicalData,
            (
                'inherited_id',
                'sig_code',
                'disease_id',
                'rev_status',
            ),
            clinvar_data
        )
        bulk_ORM_insert(
            Disease,
            ('name',),
            [(disease,) for disease in new_diseases]
        )

    def restart_autoincrement(self, model):
        assert self.model == model
        restart_autoincrement(self.model)
        db.session.commit()
        restart_autoincrement(ClinicalData)
        db.session.commit()

    def raw_delete_all(self, model):
        assert self.model == model

        # remove diseases
        Disease.query.delete()
        # remove clinical data
        ClinicalData.query.delete()
        # then mutations
        count = self.model.query.delete()

        # count of removed mutations is more informative
        return count
