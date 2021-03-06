###############################################################################
#                                                                             #
#    This program is free software: you can redistribute it and/or modify     #
#    it under the terms of the GNU General Public License as published by     #
#    the Free Software Foundation, either version 3 of the License, or        #
#    (at your option) any later version.                                      #
#                                                                             #
#    This program is distributed in the hope that it will be useful,          #
#    but WITHOUT ANY WARRANTY; without even the implied warranty of           #
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the            #
#    GNU General Public License for more details.                             #
#                                                                             #
#    You should have received a copy of the GNU General Public License        #
#    along with this program. If not, see <http://www.gnu.org/licenses/>.     #
#                                                                             #
###############################################################################

import os
import sys
import csv
import logging
import random
from collections import defaultdict

import dendropy

from biolib.common import check_file_exists, make_sure_path_exists, is_float
from biolib.external.execute import check_dependencies
from biolib.taxonomy import Taxonomy
from biolib.newick import parse_label

from genometreetk.qc_genomes import QcGenomes
from genometreetk.select_type_genomes import SelectTypeGenomes
from genometreetk.cluster_named_types import ClusterNamedTypes
from genometreetk.cluster_de_novo import ClusterDeNovo
from genometreetk.cluster_user import ClusterUser
from genometreetk.tree_gids import TreeGIDs

from genometreetk.exceptions import GenomeTreeTkError
from genometreetk.rna_workflow import RNA_Workflow
from genometreetk.bootstrap import Bootstrap
from genometreetk.jackknife_markers import JackknifeMarkers
from genometreetk.jackknife_taxa import JackknifeTaxa
from genometreetk.combine_support import CombineSupport
from genometreetk.reroot_tree import RerootTree
from genometreetk.common import read_gtdb_metadata, read_gtdb_taxonomy
from genometreetk.phylogenetic_diversity import PhylogeneticDiversity
from genometreetk.arb import Arb
from genometreetk.derep_tree import DereplicateTree
from genometreetk.assign_genomes import AssignGenomes


csv.field_size_limit(sys.maxsize)

class OptionsParser():
    def __init__(self):
        """Initialization"""
        self.logger = logging.getLogger()

    def _read_config_file(self):
        """Read configuration info."""

        cfg_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', 'genometreetk.cfg')

        d = {}
        for line in open(cfg_file):
            key, value = line.split('=')
            d[key] = value.strip()

        return d

    def ssu_tree(self, options):
        """Infer 16S tree spanning GTDB genomes."""

        check_dependencies(['mothur', 'ssu-align', 'ssu-mask', 'FastTreeMP', 'blastn'])

        check_file_exists(options.gtdb_metadata_file)
        check_file_exists(options.gtdb_ssu_file)
        make_sure_path_exists(options.output_dir)

        rna_workflow = RNA_Workflow(options.cpus)
        rna_workflow.run('ssu',
                            options.gtdb_metadata_file,
                            options.gtdb_ssu_file,
                            options.min_ssu_length,
                            options.min_scaffold_length,
                            options.min_quality,
                            options.max_contigs,
                            options.min_N50,
                            not options.disable_tax_filter,
                            options.genome_list,
                            options.output_dir,
                            options.align_method)

        self.logger.info('Results written to: %s' % options.output_dir)
        
    def lsu_tree(self, options):
        """Infer 23S tree spanning GTDB genomes."""

        check_dependencies(['esl-sfetch', 'cmsearch', 'cmalign', 'esl-alimask', 'FastTreeMP', 'blastn'])

        check_file_exists(options.gtdb_metadata_file)
        check_file_exists(options.gtdb_lsu_file)
        make_sure_path_exists(options.output_dir)

        rna_workflow = RNA_Workflow(options.cpus)
        rna_workflow.run('lsu',
                            options.gtdb_metadata_file,
                            options.gtdb_lsu_file,
                            options.min_lsu_length,
                            options.min_scaffold_length,
                            options.min_quality,
                            options.max_contigs,
                            options.min_N50,
                            not options.disable_tax_filter,
                            #options.reps_only,
                            #options.user_genomes,
                            options.genome_list,
                            options.output_dir)

        self.logger.info('Results written to: %s' % options.output_dir)
        
    def rna_tree(self, options):
        """Infer 16S + 23S tree spanning GTDB genomes."""

        check_dependencies(['FastTreeMP'])

        check_file_exists(options.ssu_msa)
        check_file_exists(options.ssu_tree)
        check_file_exists(options.lsu_msa)
        check_file_exists(options.lsu_tree)
        make_sure_path_exists(options.output_dir)

        rna_workflow = RNA_Workflow(options.cpus)
        rna_workflow.combine(options.ssu_msa,
                                options.ssu_tree,
                                options.lsu_msa,
                                options.lsu_tree,
                                options.output_dir)

        self.logger.info('Results written to: %s' % options.output_dir)
        
    def rna_dump(self, options):
        """Dump all 5S, 16S, and 23S sequences to files."""
        
        check_file_exists(options.genomic_file)
        make_sure_path_exists(options.output_dir)
        
        rna_workflow = RNA_Workflow(1)
        rna_workflow.dump(options.genomic_file,
                            options.gtdb_taxonomy,
                            options.min_5S_len,
                            options.min_16S_ar_len,
                            options.min_16S_bac_len,
                            options.min_23S_len,
                            options.min_contig_len,
                            options.include_user,
                            options.genome_list,
                            options.output_dir)
                            
        self.logger.info('Results written to: %s' % options.output_dir)
        
    def derep_tree(self, options):
        """Dereplicate tree."""
        
        check_file_exists(options.input_tree)
        check_file_exists(options.gtdb_metadata)
        check_file_exists(options.msa_file)
        make_sure_path_exists(options.output_dir)
        
        derep_tree = DereplicateTree()
        derep_tree.run(options.input_tree,
                        options.lineage_of_interest,
                        options.outgroup,
                        options.gtdb_metadata,
                        options.taxa_to_retain,
                        options.msa_file,
                        options.keep_unclassified,
                        options.output_dir)

    def bootstrap(self, options):
        """Bootstrap multiple sequence alignment."""

        check_file_exists(options.input_tree)
        if options.msa_file != 'NONE':
            check_file_exists(options.msa_file)
        make_sure_path_exists(options.output_dir)

        bootstrap = Bootstrap(options.cpus)
        output_tree = bootstrap.run(options.input_tree,
                                    options.msa_file,
                                    options.num_replicates,
                                    options.model,
                                    options.base_type,
                                    options.fraction,
                                    options.boot_dir,
                                    options.output_dir)

        self.logger.info('Bootstrapped tree written to: %s' % output_tree)

    def jk_markers(self, options):
        """Jackknife marker genes."""

        check_file_exists(options.input_tree)
        if options.msa_file != 'NONE':
            check_file_exists(options.msa_file)
        make_sure_path_exists(options.output_dir)

        jackknife_markers = JackknifeMarkers(options.cpus)
        output_tree = jackknife_markers.run(options.input_tree,
                                                options.msa_file,
                                                options.marker_info_file,
                                                options.mask_file,
                                                options.perc_markers,
                                                options.num_replicates,
                                                options.model,
                                                options.jk_dir,
                                                options.output_dir)

        self.logger.info('Jackknifed marker tree written to: %s' % output_tree)

    def jk_taxa(self, options):
        """Jackknife taxa."""

        check_file_exists(options.input_tree)
        check_file_exists(options.msa_file)
        make_sure_path_exists(options.output_dir)

        jackknife_taxa = JackknifeTaxa(options.cpus)
        output_tree = jackknife_taxa.run(options.input_tree,
                                            options.msa_file,
                                            options.outgroup_ids,
                                            options.perc_taxa,
                                            options.num_replicates,
                                            options.model,
                                            options.output_dir)

        self.logger.info('Jackknifed taxa tree written to: %s' % output_tree)

    def combine(self, options):
        """Combine support values into a single tree."""

        combineSupport = CombineSupport()
        combineSupport.run(options.support_type,
                            options.bootstrap_tree,
                            options.jk_marker_tree,
                            options.jk_taxa_tree,
                            options.output_tree)

    def support_wf(self, options):
        """"Perform entire tree support workflow."""

        self.bootstrap(options)
        self.jk_markers(options)
        self.jk_taxa(options)
        self.combine(options)

    def midpoint(self, options):
        """"Midpoint root tree."""

        reroot = RerootTree()
        reroot.midpoint(options.input_tree, options.output_tree)

    def outgroup(self, options):
        """Reroot tree with outgroup."""

        check_file_exists(options.taxonomy_file)

        self.logger.info('Identifying genomes from the specified outgroup.')
        outgroup = set()
        for genome_id, taxa in Taxonomy().read(options.taxonomy_file).iteritems():
            if options.outgroup_taxon in taxa:
                outgroup.add(genome_id)
        self.logger.info('Identifying %d genomes in the outgroup.' % len(outgroup))

        reroot = RerootTree()
        reroot.root_with_outgroup(options.input_tree, options.output_tree, outgroup)
        
    def qc_genomes(self, options):
        """Quality check all potential GTDB genomes."""
        
        check_file_exists(options.gtdb_metadata_file)
        check_file_exists(options.gtdb_user_genomes_file)
        check_file_exists(options.gtdb_user_reps)
        check_file_exists(options.ncbi_refseq_assembly_file)
        check_file_exists(options.ncbi_genbank_assembly_file)
        check_file_exists(options.gtdb_domain_report)
        make_sure_path_exists(options.output_dir)

        try:
            p = QcGenomes()
            p.run(options.gtdb_metadata_file,
                        options.gtdb_user_genomes_file,
                        options.gtdb_user_reps,
                        options.ncbi_refseq_assembly_file,
                        options.ncbi_genbank_assembly_file,
                        options.gtdb_domain_report,
                        options.min_comp,
                        options.max_cont,
                        options.min_quality,
                        options.sh_exception,
                        options.min_perc_markers,
                        options.max_contigs,
                        options.min_N50,
                        options.max_ambiguous,
                        options.output_dir)
        except GenomeTreeTkError as e:
            print e.message
            raise SystemExit

        self.logger.info('Quality checking information written to: %s' % options.output_dir)

    def select_type_genomes(self, options):
        """Select representative genomes for named species."""

        check_file_exists(options.qc_file)
        check_file_exists(options.gtdb_metadata_file)
        check_file_exists(options.genome_path_file)
        check_file_exists(options.prev_rep_file)
        check_file_exists(options.ncbi_refseq_assembly_file)
        check_file_exists(options.ncbi_genbank_assembly_file)
        check_file_exists(options.gtdb_domain_report)
        make_sure_path_exists(options.output_dir)

        try:
            p = SelectTypeGenomes(options.ani_cache_file, options.cpus, options.output_dir)
            p.run(options.qc_file,
                        options.gtdb_metadata_file,
                        options.ltp_blast_file,
                        options.genome_path_file,
                        options.prev_rep_file,
                        options.ncbi_refseq_assembly_file,
                        options.ncbi_genbank_assembly_file,
                        options.gtdb_domain_report)
        except GenomeTreeTkError as e:
            print e.message
            raise SystemExit

        self.logger.info('GTDB type genomes written to: %s' % options.output_dir)

    def cluster_named_types(self, options):
        """Cluster genomes to selected GTDB type genomes."""

        check_file_exists(options.qc_file)
        check_file_exists(options.gtdb_metadata_file)
        check_file_exists(options.genome_path_file)
        check_file_exists(options.named_type_genome_file)
        check_file_exists(options.type_genome_ani_file)
        make_sure_path_exists(options.output_dir)

        try:
            p = ClusterNamedTypes(options.ani_sp,
                                    options.af_sp,
                                    options.ani_cache_file, 
                                    options.cpus,
                                    options.output_dir)
            p.run(options.qc_file,
                    options.gtdb_metadata_file,
                    options.genome_path_file,
                    options.named_type_genome_file,
                    options.type_genome_ani_file,
                    options.mash_sketch_file)
        except GenomeTreeTkError as e:
            print e.message
            raise SystemExit

        self.logger.info('Clustering results written to: %s' % options.output_dir)
        
    def cluster_de_novo(self, options):
        """Infer de novo species clusters and type genomes for remaining genomes."""

        check_file_exists(options.qc_file)
        check_file_exists(options.gtdb_metadata_file)
        check_file_exists(options.gtdb_user_genomes_file)
        check_file_exists(options.genome_path_file)
        check_file_exists(options.type_genome_cluster_file)
        check_file_exists(options.type_genome_synonym_file)
        check_file_exists(options.ncbi_refseq_assembly_file)
        check_file_exists(options.ncbi_genbank_assembly_file)
        check_file_exists(options.ani_af_nontype_vs_type)
        make_sure_path_exists(options.output_dir)

        try:
            p = ClusterDeNovo(options.ani_sp,
                                    options.af_sp,
                                    options.ani_cache_file, 
                                    options.cpus,
                                    options.output_dir)
            p.run(options.qc_file,
                        options.gtdb_metadata_file,
                        options.gtdb_user_genomes_file,
                        options.genome_path_file,
                        options.type_genome_cluster_file,
                        options.type_genome_synonym_file,
                        options.ncbi_refseq_assembly_file,
                        options.ncbi_genbank_assembly_file,
                        options.ani_af_nontype_vs_type)
        except GenomeTreeTkError as e:
            print e.message
            raise SystemExit

        self.logger.info('Clustering results written to: %s' % options.output_dir)
        
    def cluster_user(self, options):
        """Cluster User genomes to GTDB species clusters."""

        check_file_exists(options.gtdb_metadata_file)
        check_file_exists(options.genome_path_file)
        check_file_exists(options.final_cluster_file)
        check_file_exists(options.type_radius_file)
        check_file_exists(options.nontype_radius_file)
        make_sure_path_exists(options.output_dir)

        try:
            p = ClusterUser(options.ani_cache_file, 
                                options.cpus,
                                options.output_dir)
            p.run(options.gtdb_metadata_file,
                        options.genome_path_file,
                        options.final_cluster_file,
                        options.type_radius_file,
                        options.nontype_radius_file)
        except GenomeTreeTkError as e:
            print e.message
            raise SystemExit

        self.logger.info('Clustering results written to: %s' % options.output_dir)
        
    def tree_gids(self, options):
        """Determine genome IDs for test/validation tree."""

        check_file_exists(options.qc_file)
        check_file_exists(options.gtdb_metadata_file)
        check_file_exists(options.gtdb_final_clusters)

        try:
            p = TreeGIDs()
            p.run(options.qc_file,
                    options.gtdb_metadata_file,
                    options.gtdb_final_clusters,
                    options.output_dir)
        except GenomeTreeTkError as e:
            print e.message
            raise SystemExit

        self.logger.info('Results written to: %s' % options.output_dir)

    def assign(self, options):
        """Assign genomes to canonical genomes comprising GTDB reference tree."""

        check_file_exists(options.canonical_taxonomy_file)
        check_file_exists(options.full_taxonomy_file)
        check_file_exists(options.metadata_file)
        check_file_exists(options.genome_path_file)
        
        make_sure_path_exists(options.output_dir)

        try:
            assign = AssignGenomes(options.cpus, options.output_dir)
            assign.run(options.canonical_taxonomy_file,
                        options.full_taxonomy_file,
                        options.metadata_file,
                        options.genome_path_file,
                        options.user_genomes)

        except GenomeTreeTkError as e:
            print e.message
            raise SystemExit
            
    def rep_compare(self, options):
        """Compare current and previous representatives."""

        check_file_exists(options.cur_metadata_file)
        check_file_exists(options.prev_metadata_file)
        
        # get representatives in current taxonomy
        cur_gids = set()
        cur_species = set()
        cur_genera = set()
        cur_reps_taxa = {}
        cur_rep_species = set()
        cur_rep_genera = set()
        header = True
        for row in csv.reader(open(options.cur_metadata_file)):
            if header:
                header = False
                gtdb_rep_index = row.index('gtdb_representative')
                gtdb_taxonomy_index = row.index('gtdb_taxonomy')
            else:
                gid = row[0]
                cur_gids.add(gid)
                
                gtdb_taxonomy = row[gtdb_taxonomy_index]
                if gtdb_taxonomy:
                    gtdb_taxa = [t.strip() for t in row[gtdb_taxonomy_index].split(';')]
                    if gtdb_taxa[6] != 's__':
                        cur_species.add(gtdb_taxa[6])
                    if gtdb_taxa[5] != 'g__':
                        cur_genera.add(gtdb_taxa[5])

                if row[gtdb_rep_index] == 't':
                    cur_reps_taxa[gid] = gtdb_taxa
                    
                    if gtdb_taxa[6] != 's__':
                        cur_rep_species.add(gtdb_taxa[6])
                        
                    if gtdb_taxa[5] != 'g__':
                        cur_rep_genera.add(gtdb_taxa[5])
                    
        # get representatives in previous taxonomy
        prev_reps_taxa = {}
        prev_rep_species = set()
        prev_rep_genera = set()
        header = True
        for row in csv.reader(open(options.prev_metadata_file)):
            if header:
                header = False
                gtdb_rep_index = row.index('gtdb_representative')
                gtdb_taxonomy_index = row.index('gtdb_taxonomy')
            else:
                if row[gtdb_rep_index] == 't':
                    gid = row[0]
                    gtdb_taxonomy = row[gtdb_taxonomy_index]
                    if gtdb_taxonomy:
                        gtdb_taxa = [t.strip() for t in row[gtdb_taxonomy_index].split(';')]
                            
                        prev_reps_taxa[gid] = gtdb_taxa
                        
                        if gtdb_taxa[6] != 's__':
                            prev_rep_species.add(gtdb_taxa[6])
                            
                        if gtdb_taxa[5] != 'g__':
                            prev_rep_genera.add(gtdb_taxa[5])
                    
        # summarize differences
        print('No. current representatives: %d' % len(cur_reps_taxa))
        print('No. previous representatives: %d' % len(prev_reps_taxa))
        
        print('')
        print('No. current species with representatives: %d' % len(cur_rep_species))
        print('No. previous species with representatives: %d' % len(prev_rep_species))
        
        print('')
        print('No. new representatives: %d' % len(set(cur_reps_taxa) - set(prev_reps_taxa)))
        print('No. retired representatives: %d' % len(set(prev_reps_taxa) - set(cur_reps_taxa)))
        
        print('')
        print('No. new species with representative: %d' % len(cur_rep_species - prev_rep_species))
        print('No. new genera with representative: %d' % len(cur_rep_genera - prev_rep_genera))
        
        print('')
        missing_sp_reps = prev_rep_species.intersection(cur_species) - cur_rep_species
        print('No. species that no longer have a representative: %d' % len(missing_sp_reps))
        for sp in missing_sp_reps:
            print('  ' + sp)
        
        print('')
        missing_genera_reps = prev_rep_genera.intersection(cur_genera) - cur_rep_genera
        print('No. genera that no longer have a representative: %d' % len(missing_genera_reps))
        for g in missing_genera_reps:
            print('  ' + g)
        
        print('')
        deprecated_reps = set(prev_reps_taxa).intersection(cur_gids) - set(cur_reps_taxa)
        print('No. deprecated previous representatives: %d' % len(deprecated_reps))

    def fill_ranks(self, options):
        """Ensure taxonomy strings contain all 7 canonical ranks."""

        check_file_exists(options.input_taxonomy)

        fout = open(options.output_taxonomy, 'w')
        taxonomy = Taxonomy()
        t = taxonomy.read(options.input_taxonomy)

        for genome_id, taxon_list in t.iteritems():
            full_taxon_list = taxonomy.fill_missing_ranks(taxon_list)

            taxonomy_str = ';'.join(full_taxon_list)
            if not taxonomy.check_full(taxonomy_str):
                sys.exit(-1)

            fout.write('%s\t%s\n' % (genome_id, taxonomy_str))

        fout.close()

        self.logger.info('Revised taxonomy written to: %s' % options.output_taxonomy)

    def propagate(self, options):
        """Propagate labels to all genomes in a cluster."""

        check_file_exists(options.input_taxonomy)
        check_file_exists(options.metadata_file)

        # get representative genome information
        rep_metadata = read_gtdb_metadata(options.metadata_file, ['gtdb_representative',
                                                                  'gtdb_clustered_genomes'])
                                                                  
        taxonomy = Taxonomy()
        explict_tax = taxonomy.read(options.input_taxonomy)
        expanded_taxonomy = {}
        incongruent_count = 0
        for genome_id, taxon_list in explict_tax.iteritems():
            taxonomy_str = ';'.join(taxon_list)

            # Propagate taxonomy strings if genome is a representatives. Also, determine
            # if genomes clustered together have compatible taxonomies. Note that a genome
            # may not have metadata as it is possible a User has removed a genome that is
            # in the provided taxonomy file.
            _rep_genome, clustered_genomes = rep_metadata.get(genome_id, (None, None))
            if clustered_genomes:  # genome is a representative
                clustered_genome_ids = clustered_genomes.split(';')

                # get taxonomy of all genomes in cluster with a specified taxonomy
                clustered_genome_tax = {}
                for cluster_genome_id in clustered_genome_ids:
                    if cluster_genome_id == genome_id:
                        continue

                    if cluster_genome_id not in rep_metadata:
                        continue  # genome is no longer in the GTDB so ignore it

                    if cluster_genome_id in explict_tax:
                        clustered_genome_tax[cluster_genome_id] = explict_tax[cluster_genome_id]

                # determine if representative and clustered genome taxonomy strings are congruent
                working_cluster_taxonomy = list(taxon_list)
                incongruent_with_rep = False
                for cluster_genome_id, cluster_tax in clustered_genome_tax.iteritems():
                    if incongruent_with_rep:
                        working_cluster_taxonomy = list(taxon_list)  # default to rep taxonomy
                        break

                    for r in xrange(0, len(Taxonomy.rank_prefixes)):
                        if cluster_tax[r] == Taxonomy.rank_prefixes[r]:
                            break  # no more taxonomy information to consider

                        if cluster_tax[r] != taxon_list[r]:
                            if taxon_list[r] == Taxonomy.rank_prefixes[r]:
                                # clustered genome has a more specific taxonomy string which
                                # should be propagate to the representative if all clustered
                                # genomes are in agreement
                                if working_cluster_taxonomy[r] == Taxonomy.rank_prefixes[r]:
                                    # make taxonomy more specific based on genomes in cluster
                                    working_cluster_taxonomy[r] = cluster_tax[r]
                                elif working_cluster_taxonomy[r] != cluster_tax[r]:
                                    # not all genomes agree on the assignment of this rank so leave it unspecified
                                    working_cluster_taxonomy[r] = Taxonomy.rank_prefixes[r]
                                    break
                            else:
                                # genomes in cluster have incongruent taxonomies so defer to representative
                                self.logger.warning("Genomes in cluster have incongruent taxonomies.")
                                self.logger.warning("Representative %s: %s" % (genome_id, taxonomy_str))
                                self.logger.warning("Clustered genome %s: %s" % (cluster_genome_id, ';'.join(cluster_tax)))
                                self.logger.warning("Deferring to taxonomy specified for representative.")

                                incongruent_count += 1
                                incongruent_with_rep = True
                                break

                cluster_taxonomy_str = ';'.join(working_cluster_taxonomy)

                # assign taxonomy to representative and all genomes in the cluster
                expanded_taxonomy[genome_id] = cluster_taxonomy_str
                for cluster_genome_id in clustered_genome_ids:
                    expanded_taxonomy[cluster_genome_id] = cluster_taxonomy_str
            else:
                if genome_id in expanded_taxonomy:
                    # genome has already been assigned a taxonomy based on its representative
                    pass
                else:
                    # genome is a singleton
                    expanded_taxonomy[genome_id] = taxonomy_str


        self.logger.info('Identified %d clusters with incongruent taxonomies.' % incongruent_count)

        fout = open(options.output_taxonomy, 'w')
        for genome_id, taxonomy_str in expanded_taxonomy.iteritems():
            fout.write('%s\t%s\n' % (genome_id, taxonomy_str))
        fout.close()

        self.logger.info('Taxonomy written to: %s' % options.output_taxonomy)

    def strip(self, options):
        """Remove taxonomic labels from tree."""

        check_file_exists(options.input_tree)

        outgroup_in_tree = set()
        tree = dendropy.Tree.get_from_path(options.input_tree,
                                            schema='newick',
                                            rooting='force-rooted',
                                            preserve_underscores=True)

        for node in tree.internal_nodes():
            if node.label:
                if ':' in node.label:
                    support, _taxa = node.label.split(':')
                    node.label = support

        tree.write_to_path(options.output_tree,
                            schema='newick',
                            suppress_rooting=True,
                            unquoted_underscores=True)

        self.logger.info('Stripped tree written to: %s' % options.output_tree)
        
    def pull(self, options):
        """Create taxonomy file from a decorated tree."""

        check_file_exists(options.input_tree)

        if options.no_validation:
            tree = dendropy.Tree.get_from_path(options.input_tree, 
                                                schema='newick', 
                                                rooting="force-rooted", 
                                                preserve_underscores=True)

            taxonomy = {}
            for leaf in tree.leaf_node_iter():
                taxon_id = leaf.taxon.label
                
                node = leaf.parent_node
                taxa = []
                while node:
                    support, taxon, aux_info = parse_label(node.label)
                    if taxon:
                        for t in map(str.strip, taxon.split(';'))[::-1]:
                            taxa.append(t)
                    node = node.parent_node
                    
                taxonomy[taxon_id] = taxa[::-1]
        else:
            taxonomy = Taxonomy().read_from_tree(options.input_tree)
                                                
        Taxonomy().write(taxonomy, options.output_taxonomy)
            
        self.logger.info('Stripped tree written to: %s' % options.output_taxonomy)
        
    def append(self, options):
        """Append command"""
        
        check_file_exists(options.input_tree)
        check_file_exists(options.input_taxonomy)

        taxonomy = Taxonomy().read(options.input_taxonomy)

        tree = dendropy.Tree.get_from_path(options.input_tree, 
                                            schema='newick', 
                                            rooting='force-rooted', 
                                            preserve_underscores=True)
        
        for n in tree.leaf_node_iter():
            taxa_str = taxonomy.get(n.taxon.label, None)
            if taxa_str == None:
                self.logger.error('Taxonomy file does not contain an entry for %s.' % n.label)
                sys.exit(-1)
            n.taxon.label = n.taxon.label + '|' + '; '.join(taxonomy[n.taxon.label])

        tree.write_to_path(options.output_tree, 
                            schema='newick', 
                            suppress_rooting=True, 
                            unquoted_underscores=True)

        self.logger.info('Decorated tree written to: %s' % options.output_tree)
        
    def phylogenetic_diversity(self, options):
        """Calculate phylogenetic diversity of extant taxa."""
        
        check_file_exists(options.tree)
        check_file_exists(options.taxa_list)
        
        pd = PhylogeneticDiversity()
        rtn = pd.pd(options.tree, options.taxa_list, options.rep_list, options.per_taxa_pg_file)
        
        total_pd, in_taxa, in_taxa_derep, in_pd, out_taxa, out_taxa_derep, out_pd = rtn
        total_taxa = in_taxa + out_taxa
        total_taxa_derep = in_taxa_derep + out_taxa_derep
        in_pg = total_pd - out_pd
                                            
        # report phylogenetic diversity (PD) and gain (PG)
        print ''
        print '\tNo. Taxa\tNo. Dereplicated Taxa\tPD\tPercent PD'
        
        print '%s\t%d\t%d\t%.2f\t%.2f%%' % ('Full tree', total_taxa, total_taxa_derep, total_pd, 100)
        
        print '%s\t%d\t%d\t%.2f\t%.3f%%' % ('Outgroup taxa (PD)',
                                            out_taxa,
                                            out_taxa_derep,
                                            out_pd, 
                                            out_pd * 100 / total_pd)

        print '%s\t%d\t%d\t%.2f\t%.3f%%' % ('Ingroup taxa (PD)',
                                            in_taxa,
                                            in_taxa_derep,
                                            in_pd, 
                                            (in_pd) * 100 / total_pd)   
                                        
        print '%s\t%d\t%d\t%.2f\t%.3f%%' % ('Ingroup taxa (PG)',
                                            in_taxa,
                                            in_taxa_derep,
                                            in_pg, 
                                            in_pg * 100 / total_pd)
                  
    def phylogenetic_diversity_clade(self, options):
        """Calculate phylogenetic diversity of named groups."""

        check_file_exists(options.decorated_tree)
        
        pd = PhylogeneticDiversity()
        pd.pd_clade(options.decorated_tree, options.output_file, options.taxa_list, options.rep_list)
        
        
    def arb_records(self, options):
        """Create an ARB records file from GTDB metadata."""

        check_file_exists(options.metadata_file)
        
        arb = Arb()
        arb.create_records(options.metadata_file, 
                            options.msa_file, 
                            options.taxonomy_file, 
                            options.genome_list, 
                            options.output_file)

    def parse_options(self, options):
        """Parse user options and call the correct pipeline(s)"""

        logging.basicConfig(format='', level=logging.INFO)

        check_dependencies(('FastTree', 'hmmsearch'))

        if options.subparser_name == 'ssu_tree':
            self.ssu_tree(options)
        elif options.subparser_name == 'lsu_tree':
            self.lsu_tree(options)
        elif options.subparser_name == 'rna_tree':
            self.rna_tree(options)
        elif options.subparser_name == 'rna_dump':
            self.rna_dump(options)
        elif options.subparser_name == 'derep_tree':
            self.derep_tree(options)
        elif options.subparser_name == 'bootstrap':
            self.bootstrap(options)
        elif options.subparser_name == 'jk_markers':
            self.jk_markers(options)
        elif options.subparser_name == 'jk_taxa':
            self.jk_taxa(options)
        elif options.subparser_name == 'combine':
            self.combine(options)
        elif options.subparser_name == 'midpoint':
            self.midpoint(options)
        elif options.subparser_name == 'outgroup':
            self.outgroup(options)
        elif options.subparser_name == 'qc_genomes':
            self.qc_genomes(options)
        elif options.subparser_name == 'select_type_genomes':
            self.select_type_genomes(options)
        elif options.subparser_name == 'cluster_named_types':
            self.cluster_named_types(options)
        elif options.subparser_name == 'cluster_de_novo':
            self.cluster_de_novo(options)
        elif options.subparser_name == 'cluster_user':
            self.cluster_user(options)
        elif options.subparser_name == 'tree_gids':
            self.tree_gids(options)
        elif options.subparser_name == 'assign':
            self.assign(options)
        elif options.subparser_name == 'rep_compare':
            self.rep_compare(options)
        elif options.subparser_name == 'propagate':
            self.propagate(options)
        elif options.subparser_name == 'fill_ranks':
            self.fill_ranks(options)
        elif options.subparser_name == 'strip':
            self.strip(options)
        elif options.subparser_name == 'pull':
            self.pull(options)
        elif options.subparser_name == 'append':
            self.append(options)
        elif options.subparser_name == 'pd':
            self.phylogenetic_diversity(options)
        elif options.subparser_name == 'pd_clade':
            self.phylogenetic_diversity_clade(options)
        elif options.subparser_name == 'arb_records':
            self.arb_records(options)
        else:
            self.logger.error('Unknown GenomeTreeTk command: ' + options.subparser_name + '\n')
            sys.exit()

        return 0
