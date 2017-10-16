from abc import ABC, abstractmethod
from collections import defaultdict

from Levenshtein import distance
from sqlalchemy import and_

from models import Protein, UniprotEntry, ProteinReferences
from models import Gene
from database import db


class GeneMatch:

    def __init__(self, gene=None, scored_matches=None, matched_isoforms=None):
        self.gene = gene
        self.matches = scored_matches or {}
        self.matched_isoforms = matched_isoforms or []

    @classmethod
    def from_feature(cls, gene, matched_feature, match_score, matched_isoforms=None):
        return cls(gene, {matched_feature: match_score}, matched_isoforms)

    @property
    def best_score(self):
        """Score is based on edit distance. Less is better."""
        return min(self.matches.values())

    def __iadd__(self, other):
        if not self.gene:
            self.gene = other.gene

        assert self.gene == other.gene

        for feature, score in other.matches.items():
            if feature in self.matches:
                self.matches[feature] = min(self.matches[feature], score)
            else:
                self.matches[feature] = score

        self.matched_isoforms.extend(other.matched_isoforms)

        return self

    def __getattr__(self, key):
        return getattr(self.gene, key)


class GeneOrProteinSearch(ABC):

    @abstractmethod
    def search(self, phrase, sql_filters=None, limit=None):
        pass


class GeneSearch(GeneOrProteinSearch):

    @property
    @abstractmethod
    def name(self):
        """Name of the GeneSearch descendant."""
        pass

    @property
    @abstractmethod
    def feature(self):
        """Name of the feature analysed by this GeneSearch."""
        return ''

    def get_feature(self, gene):
        return getattr(gene, self.feature)

    def search(self, phrase, sql_filters=None, limit=None):
        """Perform look up for a gene using provided phrase.

        The default implementation uses `get_feature`
        to perform search using the defined feature.

        If isoform-level filters are applied, these will
        be executed on the preferred_isoform of gene.
        """

        feature = self.get_feature(Gene)
        filters = [feature.like(phrase.strip() + '%')]

        if sql_filters:
            filters += sql_filters

        orm_query = (
            Gene.query
                .join(Protein, Gene.preferred_isoform)   # to allow PTM filter
                .filter(and_(*filters))
        )

        if limit:
            orm_query = orm_query.limit(limit)

        return [
            GeneMatch.from_feature(gene, self.name, self.sort_key(gene, phrase))
            for gene in orm_query
        ]

    def sort_key(self, gene, phrase):
        return distance(self.get_feature(gene), phrase)


class SymbolGeneSearch(GeneSearch):
    """Look up a gene by HGNC symbol

    Targets: Gene.name
    Example:
        search for "TP53" should return TP53 (among others)
    """

    name = 'gene_symbol'
    feature = 'name'


class GeneNameSearch(GeneSearch):
    """Look up a gene by full name, defined by HGNC

    Targets: Gene.full_name
    Example:
        search for "tumour protein" should return TP53 (among others)
    """

    name = 'gene_name'
    feature = 'full_name'


class IsoformBasedSearch(GeneOrProteinSearch):
    """Looks up a gene, based on a feature of its isoforms.

    The matched isoforms are recorded in GeneMatch object.
    """

    @staticmethod
    def create_query(limit, filters, entities=(Gene, Protein), add_joins=lambda query: query):
        genes = (
            add_joins(
                Gene.query
                .join(Protein, Gene.isoforms)
            )
            .filter(and_(*filters))
            .group_by(Gene)
        )

        if limit:
            genes = genes.limit(limit)

        genes = genes.subquery('genes')

        query = (
            add_joins(
                db.session.query(*entities)
                .select_from(Gene)
                .join(Protein, Gene.isoforms)
            )
            .filter(and_(*filters))
            .filter(Gene.id == genes.c.id)
        )
        return query


class RefseqGeneSearch(IsoformBasedSearch):
    """Look up a gene by isoforms RefSeq.

    Only numeric phrases and phrases starting with:
    "NM_" or "nm_" will be evaluated.

    Targets: Protein.refseq
    Example:
        search for "NM_00054" should return: TP53 [with matched
        isoforms = Protein(refseq=NM_000546)] (among others)
    """

    name = 'refseq'

    def search(self, phrase, sql_filters=None, limit=None):

        if phrase.isnumeric():
            phrase = 'NM_' + phrase

        if not (phrase.startswith('NM_') or phrase.startswith('nm_')):
            return []

        matches = []

        filters = [Protein.refseq.like(phrase + '%')]

        if sql_filters:
            filters += sql_filters

        query = self.create_query(limit, filters)

        # aggregate by genes
        isoforms_by_gene = defaultdict(set)
        for gene, isoform in query:
            isoforms_by_gene[gene].add(isoform)

        for gene, isoforms in isoforms_by_gene.items():

            match = GeneMatch.from_feature(
                gene,
                self.name,
                min(
                    self.sort_key(isoform, phrase)
                    for isoform in isoforms
                ),
                matched_isoforms=isoforms
            )
            matches.append(match)

        return matches

    @staticmethod
    def sort_key(isoform, phrase):
        return distance(isoform.refseq, phrase)


class UniprotSearch(IsoformBasedSearch):
    """Look up a gene by isoforms Uniprot accession.

    Only phrases longer than 2 characters will be evaluated.

    Targets: Protein.external_references.uniprot_entries
    """

    name = 'uniprot'

    def search(self, phrase, sql_filters=None, limit=None):

        if len(phrase) < 3:
            return []

        matches = []

        filters = [UniprotEntry.accession.like(phrase + '%')]

        if sql_filters:
            filters += sql_filters

        def add_joins(q):
            return q.join(ProteinReferences).join(UniprotEntry)

        query = self.create_query(limit, filters, (Gene, Protein, UniprotEntry), add_joins)

        # aggregate by genes
        results_by_gene = defaultdict(set)

        for gene, isoform, uniprot in query:
            results_by_gene[gene].add((isoform, uniprot))

        for gene, results in results_by_gene.items():
            isoforms, uniprot_entries = zip(*results)

            match = GeneMatch.from_feature(
                gene,
                self.name,
                min(
                    self.sort_key(uniprot, phrase)
                    for uniprot in uniprot_entries
                ),
                matched_isoforms=isoforms
            )
            matches.append(match)

        return matches

    @staticmethod
    def sort_key(uniprot, phrase):
        return distance(uniprot.accession, phrase)


feature_engines = {
    RefseqGeneSearch,
    SymbolGeneSearch,
    GeneNameSearch,
    UniprotSearch,
}

search_features = {
    engine.name: engine()
    for engine in feature_engines
}