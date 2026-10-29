"""Fixed CPU author commands; every energy retains method, composition and solvent."""
import hashlib
import importlib.metadata
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys


def save(path, body):
    p=path.with_suffix('.tmp');p.write_text(json.dumps(body,allow_nan=False));p.replace(path)


def parse_xyz(raw, expected_symbols):
    lines=raw.splitlines();position=0;structures=[]
    while position<len(lines):
        if not lines[position].strip():position+=1;continue
        count=int(lines[position]);frame=lines[position:position+count+2]
        if len(frame)!=count+2:raise ValueError('Truncated XYZ output.')
        atoms=[line.split()for line in frame[2:]]
        if [a[0]for a in atoms]!=expected_symbols:raise ValueError('Author output atom order/composition changed.')
        coordinates=[[float(x)for x in a[1:4]]for a in atoms]
        if any(len(a)!=4 for a in atoms)or not all(math.isfinite(x)for row in coordinates for x in row):
            raise ValueError('Invalid author coordinates.')
        try:energy=float(frame[1].strip())
        except ValueError:energy=None
        if energy is not None and not math.isfinite(energy):raise ValueError('Nonfinite energy.')
        structures.append({'xyz':'\n'.join(frame)+'\n','comment':frame[1], 'energy_hartree':energy})
        position+=count+2
    return structures


def main():
    incoming,output=map(Path,sys.argv[1:]);data=json.loads(incoming.read_text());r=data['input'];cfg=data['runtime']
    from rdkit import Chem
    if importlib.metadata.version('rdkit')!=cfg['rdkit_version']:raise ValueError('RDKit runtime differs.')
    method='GFN2-xTB'if r['tool']=='xtb_geometry'else'GFN-FF/CREST mquick'
    body={'status':'running','rows':[],'tool':r['tool'],'method':method,'solvent':r['solvent'],
          'semantic_type':'computed_geometry_or_conformer_ensemble_not_binding_or_efficacy',
          'limits':['Absolute energies of different compositions, charges, solvents or methods are not a potency ranking.',
                    'Geometry optimization and bounded mquick sampling do not prove global minimum, equilibrium populations or biological stability.',
                    'No receptor, binding affinity, BBB or efficacy is inferred; compare the quantities and assumptions to other tools before drawing conclusions.']}
    save(output.parent/'progress.json',body)
    for i,choice in enumerate(r['structures']):
        row={k:v for k,v in choice.items()if k!='sdf'}
        try:
            if hashlib.sha256(choice['sdf'].encode()).hexdigest()!=choice['sdf_sha256']:raise ValueError('SDF hash differs.')
            molecules=list(Chem.ForwardSDMolSupplier(io.BytesIO(choice['sdf'].encode()),removeHs=False))
            mol=molecules[choice['record_index']]
            if mol is None or not 2<=mol.GetNumAtoms()<=200:raise ValueError('Require 2–200 explicit atoms.')
            if Chem.GetFormalCharge(mol)!=choice['formal_charge']:raise ValueError('Saved charge differs.')
            if Chem.MolToSmiles(Chem.RemoveHs(mol),isomericSmiles=True)!=choice['smiles']:raise ValueError('Saved identity differs.')
            if sum(a.GetNumImplicitHs()for a in mol.GetAtoms()):raise ValueError('Explicit hydrogen coordinates required.')
            electrons=sum(a.GetAtomicNum()for a in mol.GetAtoms())-choice['formal_charge']
            if (electrons-r['unpaired_electrons'])%2:raise ValueError('Electron count and spin parity disagree.')
            folder=output.parent/f'state-{i}';folder.mkdir();xyz=Chem.MolToXYZBlock(mol);(folder/'input.xyz').write_text(xyz)
            if r['tool']=='xtb_geometry':
                cmd=[cfg['bin_directory']+'/xtb','input.xyz','--gfn','2','--opt','normal','--chrg',str(choice['formal_charge']),'--uhf',str(r['unpaired_electrons'])]
                if r['solvent']=='water':cmd+=['--alpb','water']
                filename='xtbopt.xyz'
            else:
                if r['unpaired_electrons']!=0:raise ValueError('Current GFN-FF adapter requires closed-shell input.')
                cmd=[cfg['bin_directory']+'/crest','input.xyz','--gfnff','--mquick','--chrg',str(choice['formal_charge']),'-T','1'];filename='crest_conformers.xyz'
            row.update(command=cmd,input_xyz_sha256=hashlib.sha256(xyz.encode()).hexdigest())
            with(folder/'author.log').open('wb')as log:
                p=subprocess.run(cmd,cwd=folder,stdout=log,stderr=subprocess.STDOUT,check=False)
            row['returncode']=p.returncode
            if p.returncode:raise ValueError('Author command failed; original output retained.')
            if r['tool']=='xtb_geometry'and not(folder/'.xtboptok').exists():raise ValueError('xTB convergence marker missing.')
            raw=(folder/filename).read_text()
            frames=parse_xyz(raw,[a.GetSymbol()for a in mol.GetAtoms()])
            if not frames:raise ValueError('No conformers returned.')
            if r['tool']=='xtb_geometry':
                energies=re.findall(r'TOTAL ENERGY\s+([-+0-9.Ee]+)\s+Eh',(folder/'author.log').read_text())
                if not energies:raise ValueError('Final xTB energy absent.')
                energy=float(energies[-1])
                if not math.isfinite(energy):raise ValueError('Nonfinite final energy.')
                frames[-1]['energy_hartree']=energy
            row.update(status='returned',conformers=frames,conformer_count=len(frames),
                       output_xyz_sha256=hashlib.sha256(raw.encode()).hexdigest(),
                       author_log_sha256=hashlib.sha256((folder/'author.log').read_bytes()).hexdigest())
        except Exception as error:row.update(status='author_failure',error_type=type(error).__name__,error=str(error)[:500])
        body['rows'].append(row);save(output.parent/'progress.json',body)
    count=sum(x['status']=='returned'for x in body['rows'])
    body['status']='succeeded'if count==len(body['rows'])else'partial'if count else'failed'
    save(output,body)


if __name__=='__main__':main()
