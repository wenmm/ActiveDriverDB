from database import db
from database_testing import DatabaseTest
from imports.sites.hprd import HPRDImporter
from miscellaneous import make_named_temp_file
from models import Gene
from test_imports.test_proteins import create_test_proteins

SEQUENCES = """\
>00001|00001_1|NP_000680.2|Aldehyde dehydrogenase 1
MSSSGTPDLPVLLTDLKIQYTKIFINNEWHDSVSGKKFPVFNPATEEELCQVEEGDKEDVDKAVKAARQAFQIGSPWRTMDASERGRLLYKLADLIERDRLLLATMESMNGGKLYSNAYLNDLAGCIKTLRYCAGWADKIQGRTIPIDGNFFTYTRHEPIGVCGQIIPWNFPLVMLIWKIGPALSCGNTVVVKPAEQTPLTALHVASLIKEAGFPPGVVNIVPGYGPTAGAAISSHMDIDKVAFTGSTEVGKLIKEAAGKSNLKRVTLELGGKSPCIVLADADLDNAVEFAHHGVFYHQGQCCIAASRIFVEESIYDEFVRRSVERAKKYILGNPLTPGVTQGPQIDKEQYDKILDLIESGKKEGAKLECGGGPWGNKGYFVQPTVFSNVTDEMRIAKEEIFGPVQQIMKFKSLDDVIKRANNTFYGLSAGVFTKDIDKAITISSALQAGTVWVNCYGVVSAQCPFGGFKMSGNGRELGEYGFHEYTEVKTVTVKISQKNS
>00002|00002_1|NP_001988.1|FAU
MQLFVRAQELHTFEVTGQETVAQIKAHVASLEGIAPEDQVVLLAGAPLEDEATLGQCGVEALTTLEVAGRMLGGKVHGSLARAGKVRGQTPKVAKQEKKKKKTGRAKRRMQYNRRFVNVVPTFGKKKGPNANS
>00003|00003_1|NP_000681.2|Aldehyde dehydrogenase 2
MLRAAARFGPRLGRRLLSAAATQAVPAPNQQPEVFCNQIFINNEWHDAVSRKTFPTVNPSTGEVICQVAEGDKEDVDKAVKAARAAFQLGSPWRRMDASHRGRLLNRLADLIERDRTYLAALETLDNGKPYVISYLVDLDMVLKCLRYYAGWADKYHGKTIPIDGDFFSYTRHEPVGVCGQIIPWNFPLLMQAWKLGPALATGNVVVMKVA
EQTPLTALYVANLIKEAGFPPGVVNIVPGFGPTAGAAIASHEDVDKVAFTGSTEIGRVIQVAAGSSNLKRVTLELGGKSPNIIMSDADMDWAVEQAHFALFFNQGQCCCAGSRTFVQEDIYDEFVERSVARAKSRVVGNPFDSKTEQGPQVDETQFKKILGYINTGKQEGAKLLCGGGIAADRGYFIQPTVFGDVQDGMTIAKEEIFGPVM
QILKFKTIEEVVGRANNSTYGLAAAVFTKDLDKANYLSQALQAGTVWVNCYDVFGAQSPFGGYKMSGSGRELGEYGLQAYTEVKTVTVKVPQKNS
"""

SITES = """\
00001	ALDH1A1	00001_1	NP_000680.2	2	S	-	-	Acetylation	in vitro	6427007
00002	FAU	00002_1	NP_001988.1	125	K	-	-	Acetylation	in vivo	19608861
00003	ALDH2	00003_1	NP_000681.2	480	S	-	-	Phosphorylation	in vivo	18452278
"""

MAPPINGS = """\
00001	ALDH1A1	NM_000689.3	NP_000680.2	216	100640	P00352	Aldehyde dehydrogenase 1
00002	FAU	NM_001997.3	NP_001988.1	2197	134690	P35544	FAU
00003	ALDH2	NM_000690.2	NP_000681.2	217	100650	P05091	Aldehyde dehydrogenase 2
"""


def gene_from_isoforms(all_proteins, chosen_isoforms):
    """Just for testing: in normal settings the bi-directional initialization is performed required"""
    isoforms = [protein for refseq, protein in all_proteins.items() if refseq in chosen_isoforms]
    gene = Gene(isoforms=isoforms)
    for isoform in isoforms:
        isoform.gene = gene
    return gene


class TestImport(DatabaseTest):

    def test_import(self):
        proteins = create_test_proteins(['NM_000689', 'NM_001997', 'NM_000690', 'NM_001204889'])

        # Sequence is needed for validation. Validation is tested on model level.
        sequences = {
            'NM_000689': 'MSSSGTPDLPVLLTDLKIQYTKIFINNEWHDSVSGKKFPVFNPATEEELCQVEEGDKEDVDKAVKAARQAFQIGSPWRTMDASERGRLLYKLADLIERDRLLLATMESMNGGKLYSNAYLNDLAGCIKTLRYCAGWADKIQGRTIPIDGNFFTYTRHEPIGVCGQIIPWNFPLVMLIWKIGPALSCGNTVVVKPAEQTPLTALHVASLIKEAGFPPGVVNIVPGYGPTAGAAISSHMDIDKVAFTGSTEVGKLIKEAAGKSNLKRVTLELGGKSPCIVLADADLDNAVEFAHHGVFYHQGQCCIAASRIFVEESIYDEFVRRSVERAKKYILGNPLTPGVTQGPQIDKEQYDKILDLIESGKKEGAKLECGGGPWGNKGYFVQPTVFSNVTDEMRIAKEEIFGPVQQIMKFKSLDDVIKRANNTFYGLSAGVFTKDIDKAITISSALQAGTVWVNCYGVVSAQCPFGGFKMSGNGRELGEYGFHEYTEVKTVTVKISQKNS*',
            'NM_001997': 'MQLFVRAQELHTFEVTGQETVAQIKAHVASLEGIAPEDQVVLLAGAPLEDEATLGQCGVEALTTLEVAGRMLGGKVHGSLARAGKVRGQTPKVAKQEKKKKKTGRAKRRMQYNRRFVNVVPTFGKKKGPNANS*',
            'NM_000690': 'MLRAAARFGPRLGRRLLSAAATQAVPAPNQQPEVFCNQIFINNEWHDAVSRKTFPTVNPSTGEVICQVAEGDKEDVDKAVKAARAAFQLGSPWRRMDASHRGRLLNRLADLIERDRTYLAALETLDNGKPYVISYLVDLDMVLKCLRYYAGWADKYHGKTIPIDGDFFSYTRHEPVGVCGQIIPWNFPLLMQAWKLGPALATGNVVVMKVAEQTPLTALYVANLIKEAGFPPGVVNIVPGFGPTAGAAIASHEDVDKVAFTGSTEIGRVIQVAAGSSNLKRVTLELGGKSPNIIMSDADMDWAVEQAHFALFFNQGQCCCAGSRTFVQEDIYDEFVERSVARAKSRVVGNPFDSKTEQGPQVDETQFKKILGYINTGKQEGAKLLCGGGIAADRGYFIQPTVFGDVQDGMTIAKEEIFGPVMQILKFKTIEEVVGRANNSTYGLAAAVFTKDLDKANYLSQALQAGTVWVNCYDVFGAQSPFGGYKMSGSGRELGEYGLQAYTEVKTVTVKVPQKNS*',
            'NM_001204889': 'MLRAAARFGPRLGRRLLSAAATQAVPAPNQQPEVFCNQIFINNEWHDAVSRKTFPTVNPSTGEVICQVAEGDKALETLDNGKPYVISYLVDLDMVLKCLRYYAGWADKYHGKTIPIDGDFFSYTRHEPVGVCGQIIPWNFPLLMQAWKLGPALATGNVVVMKVAEQTPLTALYVANLIKEAGFPPGVVNIVPGFGPTAGAAIASHEDVDKVAFTGSTEIGRVIQVAAGSSNLKRVTLELGGKSPNIIMSDADMDWAVEQAHFALFFNQGQCCCAGSRTFVQEDIYDEFVERSVARAKSRVVGNPFDSKTEQGPQVDETQFKKILGYINTGKQEGAKLLCGGGIAADRGYFIQPTVFGDVQDGMTIAKEEIFGPVMQILKFKTIEEVVGRANNSTYGLAAAVFTKDLDKANYLSQALQAGTVWVNCYDVFGAQSPFGGYKMSGSGRELGEYGLQAYTEVKTVTVKVPQKNS*'
        }

        for isoform, sequence in sequences.items():
            proteins[isoform].sequence = sequence

        db.session.add_all(proteins.values())

        # Add gene to test cross-isoform mapping
        aldh2 = gene_from_isoforms(proteins, ['NM_000690', 'NM_001204889'])
        db.session.add(aldh2)

        importer = HPRDImporter(make_named_temp_file(SEQUENCES), make_named_temp_file(MAPPINGS), dir_path='')

        assert len(importer.mappings) == 3

        sites = importer.load_sites(path=make_named_temp_file(SITES))

        # should have 3 pre-defined sites and one mapped (isoform NM_001204889)
        assert len(sites) == 3 + 1

        sites_by_isoform = {site.protein.refseq: site for site in sites}

        assert sites_by_isoform['NM_001204889'].residue == sites_by_isoform['NM_000690'].residue == 'S'

