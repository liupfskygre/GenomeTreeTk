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
import csv
import sys
import ntpath
from collections import defaultdict, namedtuple

from numpy import (mean as np_mean)

from genometreetk.common import read_gtdb_metadata


NCBI_TYPE_SPECIES = set(['assembly from type material', 
                                        'assembly from neotype material',
                                        'assembly designated as neotype'])
NCBI_PROXYTYPE = set(['assembly from proxytype material'])
NCBI_TYPE_SUBSP = set(['assembly from synonym type material'])

GTDB_TYPE_SPECIES = set(['type strain of species', 'type strain of neotype'])
GTDB_TYPE_SUBSPECIES = set(['type strain of subspecies', 'type strain of heterotypic synonym'])
GTDB_NOT_TYPE_MATERIAL = set(['not type material'])


def parse_canonical_sp(sp):
    """Get canonical binomial species name."""
    
    sp = sp.replace('Candidatus ', '')
    sp = ' '.join(sp.split()[0:2]).strip()
    
    return sp
        

def symmetric_ani(ani_af, gid1, gid2):
    """Calculate symmetric ANI statistics between genomes."""
    
    if (gid1 not in ani_af
        or gid2 not in ani_af 
        or gid1 not in ani_af[gid2]
        or gid2 not in ani_af[gid1]):
        return 0.0, 0.0
    
    cur_ani, cur_af = ani_af[gid1][gid2]
    rev_ani, rev_af = ani_af[gid2][gid1]
    
    # ANI should be the larger of the two values as this
    # is the most conservative circumscription and reduces the
    # change of creating polyphyletic species clusters
    ani = max(rev_ani, cur_ani)
    
    # AF should be the larger of the two values in order to 
    # accomodate incomplete and contaminated genomes
    af = max(rev_af, cur_af)
    
    return ani, af
    
    
def quality_score(gids, quality_metadata):
    """"Calculate quality score for genomes."""

    score = {}
    for gid in gids:
        metadata = quality_metadata[gid]
    
        # check if genome appears to complete consist of only an unspanned
        # chromosome and unspanned plasmids and thus should be considered
        # very high quality
        if (metadata.ncbi_assembly_level 
                and metadata.ncbi_assembly_level.lower() in ['complete genome', 'chromosome']
                and metadata.ncbi_genome_representation
                and metadata.ncbi_genome_representation.lower() == 'full'
                and metadata.scaffold_count == metadata.ncbi_molecule_count
                and metadata.ncbi_unspanned_gaps == 0
                and metadata.ncbi_spanned_gaps <= 10
                and metadata.ambiguous_bases <= 1e4
                and metadata.total_gap_length <= 1e4
                and metadata.ssu_count >= 1):
            q = 100
        else:
            q = 0
            
        q += metadata.checkm_completeness - 5*metadata.checkm_contamination
        q += 200*(metadata.ncbi_type_material_designation is not None 
                    and metadata.ncbi_type_material_designation.lower() in NCBI_TYPE_SPECIES)
        q += 10*((metadata.ncbi_type_material_designation is not None 
                    and metadata.ncbi_type_material_designation.lower() in NCBI_PROXYTYPE)
                  or (metadata.ncbi_refseq_category is not None 
                    and ('representative' in metadata.ncbi_refseq_category.lower()
                        or 'reference' in metadata.ncbi_refseq_category.lower())))

        q -= 5*float(metadata.contig_count)/100
        q -= 5*float(metadata.ambiguous_bases)/1e5
        
        if metadata.ncbi_genome_category:
            if 'metagenome' in metadata.ncbi_genome_category.lower():
                q -= 200
            if 'single cell' in metadata.ncbi_genome_category.lower():
                q -= 100
        
        # check for near-complete 16S rRNA gene
        gtdb_domain = metadata.gtdb_taxonomy[0]
        min_ssu_len = 1200
        if gtdb_domain == 'd__Archaea':
            min_ssu_len = 900
            
        if metadata.ssu_length and metadata.ssu_length >= min_ssu_len:
            q += 10
            
        score[gid] = q
        
    return score
    
    
def parse_marker_percentages(gtdb_domain_report):
    """Parse percentage of marker genes for each genome."""
    
    marker_perc = {}
    with open(gtdb_domain_report) as f:
        header = f.readline().rstrip().split('\t')
        
        domain_index = header.index('Predicted domain')
        bac_marker_perc_index = header.index('Bacterial Marker Percentage')
        ar_marker_perc_index = header.index('Archaeal Marker Percentage')
        
        for line in f:
            line_split = line.strip().split('\t')
            
            gid = line_split[0]
            domain = line_split[domain_index]
            
            if domain == 'd__Bacteria':
                marker_perc[gid] = float(line_split[bac_marker_perc_index])
            else:
                marker_perc[gid] = float(line_split[ar_marker_perc_index])

    return marker_perc
    

def pass_qc(qc, 
            marker_perc,
            min_comp,
            max_cont,
            min_quality,
            sh_exception,
            min_perc_markers,
            max_contigs,
            min_N50,
            max_ambiguous,
            failed_tests):
    """Check if genome passes QC."""
    
    failed = False
    if qc.checkm_completeness < min_comp:
        failed_tests['comp'] += 1
        failed = True
    
    if qc.checkm_strain_heterogeneity_100 >= sh_exception:
        if qc.checkm_contamination > 20:
            failed_tests['cont'] += 1
            failed = True
        q = qc.checkm_completeness - 5*qc.checkm_contamination*(1.0 - qc.checkm_strain_heterogeneity_100/100.0)
        if q < min_quality:
            failed_tests['qual'] += 1
            failed = True
    else:
        if qc.checkm_contamination > max_cont:
            failed_tests['cont'] += 1
            failed = True
        q = qc.checkm_completeness - 5*qc.checkm_contamination
        if q < min_quality:
            failed_tests['qual'] += 1
            failed = True
            
    if marker_perc < min_perc_markers:
        failed_tests['marker_perc'] += 1
        failed = True
            
    if qc.contig_count > max_contigs:
        failed_tests['contig_count'] += 1
        failed = True
    if qc.n50_contigs < min_N50:
        failed_tests['N50'] += 1
        failed = True
    if qc.ambiguous_bases > max_ambiguous:
        failed_tests['ambig'] += 1
        failed = True
    
    return not failed
    
def ncbi_type_strain_of_species(type_metadata):
    """Determine genomes considered type strain of species at NCBI."""
    
    type_gids = set()
    for gid in type_metadata:
        if type_metadata[gid].ncbi_type_material_designation in NCBI_TYPE_SPECIES:
            type_gids.add(gid)
            
    return type_gids
    
    
def gtdb_type_strain_of_species(type_metadata):
    """Determine genomes considered type strain of species by GTDB."""
    
    type_gids = set()
    for gid in type_metadata:
        if type_metadata[gid].gtdb_type_designation in GTDB_TYPE_SPECIES:
            type_gids.add(gid)
            
    return type_gids
            
    
def exclude_from_refseq(refseq_assembly_file, genbank_assembly_file):
    """Parse exclude from RefSeq field from NCBI assembly files."""
    
    excluded_from_refseq_note = {}
    for assembly_file in [refseq_assembly_file, genbank_assembly_file]:
            for line in open(assembly_file):
                if line[0] == '#':
                    if line.startswith('# assembly_accession'):
                        header = line.strip().split('\t')
                        exclude_index = header.index('excluded_from_refseq')
                else:
                    line_split = line.strip('\n\r').split('\t')
                    gid = line_split[0]
                    gid = gid.replace('GCA_','GB_GCA_').replace('GCF_', 'RS_GCF_')
                    excluded_from_refseq_note[gid] = line_split[exclude_index]
    
    return excluded_from_refseq_note
    
def write_clusters(clusters, species, out_file):
    """Write out clustering information."""

    fout = open(out_file, 'w')
    fout.write('NCBI species\tType genome\tNo. clustered genomes\tMean ANI\tMin ANI\tMean AF\tMin AF\tClustered genomes\n')
    for gid in sorted(clusters, key=lambda x: len(clusters[x]), reverse=True):
        if len(clusters[gid]):
            mean_ani = '%.2f' % np_mean([d.ani for d in clusters[gid]])
            min_ani = '%.2f' % min([d.ani for d in clusters[gid]])
            mean_af = '%.2f' % np_mean([d.af for d in clusters[gid]])
            min_af = '%.2f' % min([d.af for d in clusters[gid]])
        else:
            mean_ani = min_ani = mean_af = min_af = 'N/A'
        fout.write('%s\t%s\t%d\t%s\t%s\t%s\t%s\t%s\n' % (
                        species.get(gid, 'unclassified'), 
                        gid, 
                        len(clusters[gid]),
                        mean_ani, min_ani,
                        mean_af, min_af,
                        ','.join([d.gid for d in clusters[gid]])))
    fout.close()
    
    
def read_qc_file(qc_file):
    """Read genomes passing QC from file."""
    
    passed_qc = set()
    with open(qc_file) as f:
        f.readline()
        
        for line in f:
            line_split = line.strip().split('\t')
            passed_qc.add(line_split[0])
            
    return passed_qc
    
def read_quality_metadata(metadata_file):
    """Read statistics needed to determine genome quality."""
    
    return read_gtdb_metadata(metadata_file, ['gtdb_taxonomy',
                                                'checkm_completeness',
                                                'checkm_contamination',
                                                'checkm_strain_heterogeneity_100',
                                                'genome_size',
                                                'contig_count',
                                                'n50_contigs',
                                                'scaffold_count',
                                                'ambiguous_bases',
                                                'total_gap_length',
                                                'ssu_count',
                                                'ssu_length',
                                                'mimag_high_quality',
                                                'ncbi_assembly_level',
                                                'ncbi_genome_representation',
                                                'ncbi_refseq_category',
                                                'ncbi_type_material_designation',
                                                'ncbi_molecule_count',
                                                'ncbi_unspanned_gaps',
                                                'ncbi_spanned_gaps',
                                                'ncbi_genome_category'])
                                                

def read_clusters(cluster_file):
    """Read cluster file."""
        
    clusters = defaultdict(list)
    species = {}
    with open(cluster_file) as f:
        headers = f.readline().strip().split('\t')
        
        type_sp_index = headers.index('NCBI species')
        type_genome_index = headers.index('Type genome')
        num_clustered_index = headers.index('No. clustered genomes')
        clustered_genomes_index = headers.index('Clustered genomes')
        
        for line in f:
            line_split = line.strip().split('\t')
            
            sp = line_split[type_sp_index]
            rid = line_split[type_genome_index]
            species[rid] = sp

            num_clustered = int(line_split[num_clustered_index])
            if num_clustered > 0:
                clusters[rid] = [g.strip() for g in line_split[clustered_genomes_index].split(',')]
            else:
                clusters[rid] = []
                    
    return clusters, species
    
    
def write_type_radius(type_radius, species, out_file):
    """Write out ANI radius for each type genomes."""

    fout = open(out_file, 'w')
    fout.write('NCBI species\tType genome\tANI\tAF\tClosest species\tClosest type genome\n')
    
    for gid in type_radius:
        ani, af, neighbour_gid = type_radius[gid]
        if not af:
            af = 0
            
        if not neighbour_gid:
            neighbour_gid = 'N/A'
            neighbour_sp = 'N/A'
        else:
            neighbour_sp = species[neighbour_gid]
        
        fout.write('%s\t%s\t%.2f\t%.2f\t%s\t%s\n' % (species[gid],
                                                        gid,
                                                        ani,
                                                        af,
                                                        neighbour_sp,
                                                        neighbour_gid))
    fout.close()
