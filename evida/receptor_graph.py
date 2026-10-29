"""Retain the graph established by Meeko preparation; never infer bonds from PDB."""
import copy
import hashlib
import json
import re

SCHEMA = 'meeko_prepared_receptor_graph_v1'

def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pdb_atoms(text):
    rows = []
    for line in text.splitlines():
        if line.startswith(('ATOM  ', 'HETATM')):
            rows.append({'serial': int(line[6:11]), 'name': line[12:16].strip(),
                         'residue_name': line[17:20].strip(), 'chain': line[21:22].strip(),
                         'residue_number': int(line[22:26]), 'insertion_code': line[26:27].strip(),
                         'coordinates_angstrom': [float(line[30:38]),float(line[38:46]),float(line[46:54])],
                         'element': line[76:78].strip()})
    if not rows or len({row['serial']for row in rows}) != len(rows):
        raise ValueError('Prepared PDB has no unique atom serial identity.')
    return rows


def export_prepared_graph(polymer, links, prepared_pdb):
    from rdkit import Chem
    from rdkit.Chem import rdMolInterchange
    original_rows = pdb_atoms(prepared_pdb)
    overlay = copy.copy(polymer); overlay.monomers = {}
    source_atoms = []; offset = 0
    for rid, monomer in polymer.get_valid_monomers().items():
        clone = copy.copy(monomer); clone.rdkit_mol = Chem.Mol(monomer.rdkit_mol)
        overlay.monomers[rid] = clone
        match = re.fullmatch(r'(.*):(-?\d+)([A-Za-z]?)',rid)
        if match is None:
            raise ValueError('Unmapped prepared residue identity.')
        chain, number, insertion = match.groups()
        by_rdkit = {residx: padidx for padidx,residx in monomer.molsetup_mapidx.items()}
        for index, atom in enumerate(clone.rdkit_mol.GetAtoms()):
            row = original_rows[offset]
            if (row['serial'] != offset+1 or row['name'] != monomer.atom_names[index]
                    or row['residue_name'] != monomer.input_resname or row['chain'] != chain
                    or row['residue_number'] != int(number) or row['insertion_code'] != insertion
                    or row['element'].title() != atom.GetSymbol()):
                raise ValueError('Meeko graph atom identity does not match prepared PDB.')
            full = list(monomer.rdkit_mol.GetConformer().GetAtomPosition(index))
            delta = max(abs(a-b)for a,b in zip(full,row['coordinates_angstrom']))
            if delta > 0.000501:
                raise ValueError('Prepared graph coordinate differs beyond PDB quantization.')
            info = Chem.AtomPDBResidueInfo()
            info.SetSerialNumber(row['serial']);info.SetName(row['name'].rjust(4))
            info.SetResidueName(row['residue_name']);info.SetChainId(row['chain'])
            info.SetResidueNumber(row['residue_number']);info.SetInsertionCode(row['insertion_code'])
            atom.SetMonomerInfo(info)
            partial = monomer.molsetup.atoms[by_rdkit[index]]
            source_atoms.append({**row,'meeko_residue_id':rid,'meeko_residue_atom_index':index,
                'atomic_number':atom.GetAtomicNum(),'formal_charge':atom.GetFormalCharge(),
                'isotope':atom.GetIsotope(),'aromatic':atom.GetIsAromatic(),
                'pre_pdb_coordinates_angstrom':full,'pdb_quantization_max_delta_angstrom':delta,
                'docking_partial_charge':partial.charge,'docking_atom_type':partial.atom_type,
                'docking_ignored_atom':partial.is_ignore})
            offset += 1
    if offset != len(original_rows):
        raise ValueError('Unaccounted prepared receptor atoms.')
    # Use the author's stitch operation with the exact links captured during preparation.
    # Omitting bonds_to_use would rerun spatial link perception; that path is forbidden here.
    molecule = overlay.stitch(bonds_to_use=links)
    Chem.SanitizeMol(molecule)
    serial_to_index = {}
    for atom in molecule.GetAtoms():
        serial = atom.GetPDBResidueInfo().GetSerialNumber()
        serial_to_index[serial] = atom.GetIdx()
    if set(serial_to_index) != {row['serial']for row in original_rows}:
        raise ValueError('Stitched author graph atom identity changed.')
    conformer=molecule.GetConformer()
    for row in source_atoms:
        index=serial_to_index[row['serial']]
        atom=molecule.GetAtomWithIdx(index)
        if atom.GetFormalCharge()!=row['formal_charge']or atom.GetAtomicNum()!=row['atomic_number']:
            raise ValueError('Author graph stitching changed atom identity or formal charge.')
        # The contact calculation uses precisely the PDB coordinates consumed by docking.
        # Full precision preparation coordinates remain in source_atoms as a separate record.
        conformer.SetAtomPosition(index,row['coordinates_angstrom'])
        row['rdkit_atom_index']=index
    bonds=[{'begin_atom_index':b.GetBeginAtomIdx(),'end_atom_index':b.GetEndAtomIdx(),
            'begin_pdb_serial':molecule.GetAtomWithIdx(b.GetBeginAtomIdx()).GetPDBResidueInfo().GetSerialNumber(),
            'end_pdb_serial':molecule.GetAtomWithIdx(b.GetEndAtomIdx()).GetPDBResidueInfo().GetSerialNumber(),
            'bond_type':str(b.GetBondType()),'aromatic':b.GetIsAromatic()}
           for b in molecule.GetBonds()]
    return {'schema':SCHEMA,'prepared_pdb_sha256':sha(prepared_pdb.encode()),
            'bond_source':'Meeko residue templates plus exact prepared inter-residue links; author Polymer.stitch with explicit bonds_to_use.',
            'coordinate_policy':'Exact prepared PDB coordinates used for docking; pre-PDB preparation precision retained separately.',
            'inter_residue_links':[{'left_residue':a,'right_residue':b,'atom_pairs':pairs}for(a,b),pairs in links.items()],
            'rdkit_mol_json':rdMolInterchange.MolToJSON(molecule),
            'atoms':source_atoms,'bonds':bonds,'atom_count':molecule.GetNumAtoms(),
            'bond_count':molecule.GetNumBonds(),'hydrogen_count':sum(a.GetAtomicNum()==1 for a in molecule.GetAtoms())}


def molecule_from_graph(graph, prepared_pdb):
    from rdkit import Chem
    from rdkit.Chem import rdMolInterchange
    if graph.get('schema')!=SCHEMA or graph['prepared_pdb_sha256']!=sha(prepared_pdb.encode()):
        raise ValueError('Prepared graph source binding mismatch.')
    mols=rdMolInterchange.JSONToMols(graph['rdkit_mol_json'])
    if len(mols)!=1:
        raise ValueError('Expected one preserved receptor graph.')
    molecule=mols[0]
    rows=pdb_atoms(prepared_pdb);by_serial={row['serial']:row for row in rows}
    if molecule.GetNumAtoms()!=graph['atom_count']or len(graph['atoms'])!=len(rows)or molecule.GetNumBonds()!=graph['bond_count']or len(graph['bonds'])!=graph['bond_count']:
        raise ValueError('Preserved receptor graph counts changed.')
    seen=set()
    for row in graph['atoms']:
        index=row['rdkit_atom_index'];atom=molecule.GetAtomWithIdx(index)
        if index in seen or row['serial']not in by_serial:
            raise ValueError('Preserved graph atom mapping duplicated or missing.')
        seen.add(index);source=by_serial[row['serial']]
        for key in ('name','residue_name','chain','residue_number','insertion_code','coordinates_angstrom','element'):
            if row[key]!=source[key]:raise ValueError('Prepared graph atom metadata differs from exact PDB.')
        if atom.GetAtomicNum()!=row['atomic_number']or atom.GetFormalCharge()!=row['formal_charge']or atom.GetIsotope()!=row['isotope']or atom.GetIsAromatic()!=row['aromatic']:
            raise ValueError('Preserved graph atom chemistry changed.')
        info=Chem.AtomPDBResidueInfo();info.SetSerialNumber(row['serial']);info.SetName(row['name'].rjust(4))
        info.SetResidueName(row['residue_name']);info.SetChainId(row['chain']);info.SetResidueNumber(row['residue_number']);info.SetInsertionCode(row['insertion_code']);atom.SetMonomerInfo(info)
        point=molecule.GetConformer().GetAtomPosition(index)
        if max(abs(a-b)for a,b in zip(point,source['coordinates_angstrom']))>0.000001:
            raise ValueError('Preserved graph coordinates changed.')
        molecule.GetConformer().SetAtomPosition(index,source['coordinates_angstrom'])
    seen_bonds=set()
    for bond in graph['bonds']:
        key=tuple(sorted((bond['begin_atom_index'],bond['end_atom_index'])))
        if key in seen_bonds:raise ValueError('Preserved graph bond mapping duplicated.')
        seen_bonds.add(key)
        actual=molecule.GetBondBetweenAtoms(bond['begin_atom_index'],bond['end_atom_index'])
        if actual is None or str(actual.GetBondType())!=bond['bond_type']or actual.GetIsAromatic()!=bond['aromatic']:
            raise ValueError('Preserved graph bond changed.')
    if len(seen)!=molecule.GetNumAtoms()or sum(a.GetAtomicNum()==1 for a in molecule.GetAtoms())!=graph['hydrogen_count']:
        raise ValueError('Preserved graph atom or hydrogen coverage changed.')
    Chem.SanitizeMol(molecule)
    return molecule
