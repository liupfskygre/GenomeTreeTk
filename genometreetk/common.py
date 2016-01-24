###############################################################################
#
# common.py - utility functions used in many places in CheckM
#
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
from collections import defaultdict

import biolib.seq_io as seq_io

from genometreetk.default_values import DefaultValues


def read_gtdb_genome_quality(metadata_file, keep_db_prefix=False):
    """Parse genome quality from GTDB metadata.

    Parameters
    ----------
    metadata_file : str
        Metadata, including CheckM estimates, for all genomes.

    Return
    ------
    dict : d[genome_id] -> genome_quality
    """

    genome_quality = {}

    csv_reader = csv.reader(open(metadata_file, 'rt'))
    bHeader = True
    for row in csv_reader:
        if bHeader:
            headers = row
            genome_index = headers.index('genome')
            comp_index = headers.index('checkm_completeness')
            cont_index = headers.index('checkm_contamination')
            bHeader = False
        else:
            genome_id = row[genome_index]
            if not keep_db_prefix:
                genome_id = genome_id.replace('RS_', '').replace('GB_', '')
            comp = float(row[comp_index])
            cont = float(row[cont_index])

            genome_quality[genome_id] = [comp, cont, comp - cont]

    return genome_quality


def read_gtdb_phylum(metadata_file, keep_db_prefix=False):
    """Parse GTDB phylum information from GTDB metadata.

    Parameters
    ----------
    metadata_file : str
        Metadata for all genomes.

    Return
    ------
    dict : d[genome_id] -> phyla
    """

    genome_phyla = {}

    csv_reader = csv.reader(open(metadata_file, 'rt'))
    bHeader = True
    for row in csv_reader:
        if bHeader:
            headers = row
            genome_index = headers.index('genome')
            phylum_index = headers.index('gtdb_phylum')
            bHeader = False
        else:
            genome_id = row[genome_index]
            if not keep_db_prefix:
                genome_id = genome_id.replace('RS_', '').replace('GB_', '')
            genome_phyla[genome_id] = row[phylum_index]

    return genome_phyla


def read_gtdb_taxonomy(metadata_file, keep_db_prefix=False):
    """Parse GTDB taxonomy from GTDB metadata.

    Parameters
    ----------
    metadata_file : str
        Metadata for all genomes.

    Return
    ------
    dict : d[genome_id] -> taxonomy list
    """

    taxonomy = {}

    csv_reader = csv.reader(open(metadata_file, 'rt'))
    bHeader = True
    for row in csv_reader:
        if bHeader:
            headers = row
            genome_index = headers.index('genome')
            taxonomy_index = headers.index('gtdb_taxonomy')
            bHeader = False
        else:
            genome_id = row[genome_index]
            if not keep_db_prefix:
                genome_id = genome_id.replace('RS_', '').replace('GB_', '')

            taxonomy[genome_id] = row[taxonomy_index].split(';')

    return taxonomy


def read_gtdb_ncbi_taxonomy(metadata_file, keep_db_prefix=False):
    """Parse NCBI taxonomy from GTDB metadata.

    Parameters
    ----------
    metadata_file : str
        Metadata for all genomes.

    Return
    ------
    dict : d[genome_id] -> taxonomy list
    """

    taxonomy = {}

    csv_reader = csv.reader(open(metadata_file, 'rt'))
    bHeader = True
    for row in csv_reader:
        if bHeader:
            headers = row
            genome_index = headers.index('genome')
            taxonomy_index = headers.index('ncbi_taxonomy')
            bHeader = False
        else:
            genome_id = row[genome_index]
            if not keep_db_prefix:
                genome_id = genome_id.replace('RS_', '').replace('GB_', '')

            taxonomy[genome_id] = row[taxonomy_index].split(';')

    return taxonomy


def read_gtdb_ncbi_type_strain(metadata_file, keep_db_prefix=False):
    """Parse NCBI type strain from GTDB metadata.

    Parameters
    ----------
    metadata_file : str
        Metadata for all genomes.

    Return
    ------
    set
        Set of genomes marked as type strains by NCBI.
    """

    type_strains = set()

    csv_reader = csv.reader(open(metadata_file, 'rt'))
    bHeader = True
    for row in csv_reader:
        if bHeader:
            headers = row
            genome_index = headers.index('genome')
            type_strain_index = headers.index('ncbi_type_strain')
            bHeader = False
        else:
            genome_id = row[genome_index]
            if not keep_db_prefix:
                genome_id = genome_id.replace('RS_', '').replace('GB_', '')
                
            if bool(row[type_strain_index]):
                type_strains.add(genome_id)

    return type_strains


def read_tree_model(reportFile):
    for line in open(reportFile):
        if 'Model of evolution:' in line:
            modelStr = line[line.find(':') + 1:].strip()

    return modelStr


def read_genome_dir_file(genome_dir_file):
    """Read genome directories from file.

    Parameters
    ----------
    genome_dir_file : str
        File to read.

    Returns
    -------
    dict : d[genome_id] -> directory
        Directory for each genome.
    """

    # read directory for each genome
    genome_dirs = {}
    for line in open(genome_dir_file):
        line_split = line.split('\t')
        genome_dirs[line_split[0]] = line_split[1].strip()

    return genome_dirs


def read_marker_id_file(marker_id_file):
    """Read marker ids from file.

    Parameters
    ----------
    marker_id_file : str
        File to read.

    Returns
    -------
    set
        Marker ids.
    """

    marker_genes = set()
    for line in open(marker_id_file):
        if line[0] == '#':
            continue

        marker_genes.add(line.split('\t')[0].strip())

    return marker_genes


def read_genome_id_file(genome_id_file):
    """Read genome ids from file.

    Parameters
    ----------
    genome_file : str
        File to read.

    Returns
    -------
    set
        NCBI genome ids.
    set
        User genome ids.
    """

    ncbi_genome_ids = set()
    user_genome_ids = set()
    for line in open(genome_id_file):
        if line[0] == '#':
            continue

        if '\t' in line:
            genome_id = line.split('\t')[0].strip()
        else:
            genome_id = line.split()[0].strip()

        if genome_id.startswith('U_'):
            user_genome_ids.add(genome_id)
        else:
            ncbi_genome_ids.add(genome_id)

    return ncbi_genome_ids, user_genome_ids


def create_concatenated_alignment(genome_ids,
                                   marker_genes,
                                   alignment_dir,
                                   concatenated_alignment_file,
                                   marker_file):
    """Create concatenated multiple sequence alignment for all genomes.

    Parameters
    ----------
    genome_ids : iterable
        Genomes of interest.
    marker_genes : iterable
        Unique ids of marker genes.
    alignment_dir : str
        Directory containing multiple sequence alignments.
    concatenated_alignment_file : str
        File to containing concatenated alignment.
    marker_file : str
        File indicating length of each marker in the alignment.
    """

    # Read alignment files. Some genomes may have multiple
    # copies of a marker gene in which case the last one
    # is arbitrarily taken. This is acceptable as all genes
    # are already screen to be conspecific.
    alignments = defaultdict(dict)
    marker_length = {}
    for mg in marker_genes:
        f = mg + '.aln.masked.faa'
        seqs = seq_io.read_fasta(os.path.join(alignment_dir, f))

        for seq_id, seq in seqs.iteritems():
            genome_id = seq_id[0:seq_id.find(DefaultValues.SEQ_CONCAT_CHAR)]

            alignments[mg][genome_id] = seq

            marker_length[mg] = len(seq)

    # create marker file
    fout = open(marker_file, 'w')
    for mg in marker_genes:
        fout.write('%s\t%s\t%s\t%d\n' % (mg, mg, mg, marker_length[mg]))
    fout.close()

    # create concatenated alignment
    concatenated_seqs = {}
    for mg in marker_genes:
        seqs = alignments[mg]

        for genome_id in genome_ids:
            if genome_id in seqs:
                # append alignment
                concatenated_seqs[genome_id] = concatenated_seqs.get(genome_id, '') + seqs[genome_id]
            else:
                # missing gene
                concatenated_seqs[genome_id] = concatenated_seqs.get(genome_id, '') + '-' * marker_length[mg]

    # save concatenated alignment
    seq_io.write_fasta(concatenated_seqs, concatenated_alignment_file)
