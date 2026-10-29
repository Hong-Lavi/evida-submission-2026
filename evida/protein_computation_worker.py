"""fpocket, short apo OpenMM simulation and MDAnalysis on retained inputs; CPU only."""
import base64
import hashlib
import importlib.metadata
import io
import json
import math
from pathlib import Path
import random
import re
import subprocess
import sys


def digest(raw): return hashlib.sha256(raw).hexdigest()


def protein_pdb(request):
    import gemmi
    original = gemmi.make_structure_from_block(gemmi.cif.read_string(request['cif']).sole_block())
    if len(original) != 1: raise ValueError('Explicit single coordinate model required.')
    chosen = gemmi.Structure(); model = gemmi.Model(1)
    omitted = []; selected = []; count = 0
    for chain in original[0]:
        if chain.name not in request['chain_ids']:
            omitted.append({'chain':chain.name,'reason':'unselected_chain'});continue
        if len(chain.name) != 1: raise ValueError('Current PDB author adapters require a single-character chain ID.')
        clone = chain.clone()
        for index in reversed(range(len(clone))):
            residue = clone[index]
            if residue.het_flag != 'A' or not gemmi.find_tabulated_residue(residue.name).is_amino_acid():
                omitted.append({'chain':chain.name,'residue':str(residue.seqid),'name':residue.name,'reason':'apo_nonprotein_component'})
                del clone[index];continue
            if any(atom.altloc not in ('\x00', ' ') for atom in residue):
                raise ValueError('Alternate atom locations require explicit state selection before this computation.')
            if any(atom.occ < .99 or not all(math.isfinite(v) for v in (atom.pos.x,atom.pos.y,atom.pos.z)) for atom in residue):
                raise ValueError('Incomplete occupancy or nonfinite coordinates require a reviewed model.')
            count += len(residue)
        if not len(clone):raise ValueError('Selected chain contains no supported protein residues.')
        model.add_chain(clone);selected.append(chain.name)
    if set(selected) != set(request['chain_ids']) or count > 20000:
        raise ValueError('Selected chain set is incomplete or exceeds the bounded protein input.')
    chosen.add_model(model)
    return chosen.make_pdb_string(),{'selected_chains':selected,'omitted_components':omitted,
        'input_atoms':count,'preparation':'selected protein chains only; apo; no invented missing heavy atoms/residues; no alternate-state selection'}


def pockets(request,cfg,work):
    pdb,prep=protein_pdb(request);(work/'input.pdb').write_text(pdb)
    with(work/'fpocket.log').open('wb')as log:
        proc=subprocess.run([cfg['fpocket'],'-f','input.pdb'],cwd=work,stdout=log,stderr=subprocess.STDOUT,timeout=180)
    info=work/'input_out/input_info.txt'
    if proc.returncode or not info.exists():raise ValueError('fpocket did not return a complete pocket report.')
    text=info.read_text();rows=[];row=None
    for line in text.splitlines():
        match=re.match(r'Pocket\s+(\d+)\s*:',line.strip())
        if match:
            row={'pocket_id':int(match[1]),'descriptors':{}};rows.append(row)
        elif row is not None and ':' in line:
            key,value=line.split(':',1)
            try:value=float(value.strip())
            except ValueError:value=value.strip()
            row['descriptors'][key.strip()]=value
    retained=[]
    for p in sorted((work/'input_out').rglob('*')):
        if p.is_file()and p.suffix in ('.pdb','.pqr','.txt'):
            raw=p.read_bytes()
            retained.append({'name':str(p.relative_to(work)),'sha256':digest(raw),'text':raw.decode(errors='replace')})
    return {'status':'succeeded','rows':rows,'preparation':prep,'prepared_pdb':pdb,'author_files':retained,
        'method':'fpocket4.2.3 alpha-sphere geometry; author defaults',
        'limits':['Pocket geometry and druggability descriptors are not ligand affinity, selectivity or efficacy.',
            'Apo selected chains omit ligands, waters and other assembly partners listed in preparation; biological site interpretation requires the original assembly.']}


def dynamics(request,cfg,work):
    import openmm as mm
    from openmm import app,unit
    import numpy as np
    pdb,prep=protein_pdb(request);args=request['parameters'];random.seed(args['random_seed']);np.random.seed(args['random_seed'])
    mm.Platform.getPlatformByName('CPU').setPropertyDefaultValue('Threads','1')
    structure=app.PDBFile(io.StringIO(pdb));ff=app.ForceField('amber14-all.xml','implicit/gbn2.xml')
    model=app.Modeller(structure.topology,structure.positions)
    model.addHydrogens(ff,pH=args['ph'],platform=mm.Platform.getPlatformByName('CPU'))
    system=ff.createSystem(model.topology,nonbondedMethod=app.NoCutoff,constraints=app.HBonds)
    integrator=mm.LangevinMiddleIntegrator(args['temperature_kelvin']*unit.kelvin,1/unit.picosecond,args['timestep_femtoseconds']*unit.femtoseconds)
    integrator.setRandomNumberSeed(args['random_seed'])
    simulation=app.Simulation(model.topology,system,integrator,mm.Platform.getPlatformByName('CPU'),{'Threads':'1'})
    simulation.context.setPositions(model.positions)
    simulation.minimizeEnergy(tolerance=10*unit.kilojoule_per_mole/unit.nanometer,maxIterations=500)
    simulation.context.setVelocitiesToTemperature(args['temperature_kelvin']*unit.kelvin,args['random_seed'])
    positions=simulation.context.getState(getPositions=True).getPositions()
    with(work/'topology.pdb').open('w')as f:app.PDBFile.writeFile(model.topology,positions,f,keepIds=True)
    interval=max(1,args['steps']//20)
    simulation.reporters.append(app.DCDReporter(str(work/'trajectory.dcd'),interval))
    simulation.reporters.append(app.StateDataReporter(str(work/'energies.csv'),interval,step=True,time=True,
        potentialEnergy=True,kineticEnergy=True,temperature=True,separator=','))
    completed=0
    while completed<args['steps']:
        chunk=min(1000,args['steps']-completed);simulation.step(chunk);completed+=chunk
        (work/'progress.json').write_text(json.dumps({'status':'running','rows':[], 'completed_steps':completed,'requested_steps':args['steps'],'preparation':prep}))
    state=simulation.context.getState(getPositions=True,getEnergy=True)
    energy=state.getPotentialEnergy().value_in_unit(unit.kilojoule_per_mole)
    if not math.isfinite(energy):raise ValueError('Nonfinite final potential energy.')
    del simulation
    topology=(work/'topology.pdb').read_bytes();trajectory=(work/'trajectory.dcd').read_bytes()
    if len(trajectory)>12*1024*1024:raise ValueError('Trajectory exceeds stored binary limit.')
    conditions={'forcefield':'Amber14-all + GBn2 implicit solvent','platform':'CPU','threads':1,
        'friction_per_picosecond':1,'constraints':'HBonds','nonbonded':'NoCutoff','minimization_max_iterations':500,
        'minimization_force_tolerance_kj_mol_nm':10,**args,'total_picoseconds':args['steps']*args['timestep_femtoseconds']/1000,
        'report_interval_steps':interval,'apo_selected_chains':request['chain_ids'],'missing_heavy_atoms_repaired':False,
        'disulfide_bonds':[{'residue1':str(a.residue.id),'chain1':a.residue.chain.id,
            'residue2':str(b.residue.id),'chain2':b.residue.chain.id}for a,b in model.topology.bonds()if a.name==b.name=='SG']}
    rows=[{'kind':'simulation_summary','final_potential_energy_kj_mol':energy,'atoms':model.topology.getNumAtoms(),
        'steps':args['steps'],'total_picoseconds':conditions['total_picoseconds']}]
    return {'status':'succeeded','rows':rows,'preparation':prep,'simulation_conditions':conditions,
        'trajectory_files':{'topology_pdb':{'text':topology.decode(),'sha256':digest(topology)},
            'trajectory_dcd':{'base64':base64.b64encode(trajectory).decode(),'sha256':digest(trajectory)}},
        'energy_time_series_csv':(work/'energies.csv').read_text(),
        'limits':['Short apo simulation is a local structural check, not equilibrium sampling, binding free energy, affinity or efficacy.',
            'Hydrogens follow force-field pH assignment; no missing heavy atom/residue reconstruction.',
            'No ligand, explicit water, membrane or unselected assembly partner is simulated; compare conditions before interpretation.']}


def analyze(request,cfg,work):
    import MDAnalysis as mda
    from MDAnalysis.analysis import align,rms
    import numpy as np
    (work/'topology.pdb').write_text(request['files']['topology_pdb']['text'])
    (work/'trajectory.dcd').write_bytes(base64.b64decode(request['files']['trajectory_dcd']['base64'],validate=True))
    u=mda.Universe(str(work/'topology.pdb'),str(work/'trajectory.dcd'),in_memory=True)
    select='name CA'if request['alignment']=='ca'else'backbone'
    atoms=u.select_atoms(select)
    if len(atoms)<3 or len(u.trajectory)<2:raise ValueError('At least3 alignment atoms and2 saved frames are required.')
    comparison=rms.RMSD(u,u,select=select,ref_frame=0).run().results.rmsd
    rg=[float(u.atoms.radius_of_gyration())for _ in u.trajectory]
    u.trajectory[0];align.AlignTraj(u,u,select=select,in_memory=True).run()
    fluctuations=rms.RMSF(u.select_atoms('name CA')).run().results.rmsf
    if not np.isfinite(comparison).all()or not np.isfinite(fluctuations).all():raise ValueError('Nonfinite trajectory metric.')
    rows=[{'kind':'frame','saved_frame':int(r[0]),'time_picoseconds':float(r[1]),'aligned_rmsd_angstrom':float(r[2]),
        'radius_of_gyration_angstrom':rg[i]}for i,r in enumerate(comparison)]
    rows += [{'kind':'residue_fluctuation','chain':a.segid,'residue':int(a.resid),'name':a.resname,
        'ca_rmsf_angstrom':float(v)}for a,v in zip(u.select_atoms('name CA'),fluctuations)]
    return {'status':'succeeded','rows':rows,'frames':len(u.trajectory),'atoms':len(u.atoms),
        'alignment':select,'reference':'first saved trajectory frame; not original crystal structure',
        'simulation_conditions':request['simulation_conditions'],
        'input_sha256':{k:v['sha256']for k,v in request['files'].items()},
        'limits':['RMSD/RMSF/Rg describe this short saved trajectory only, not binding affinity, efficacy or statistical convergence.',
            'Aligned trajectory retained in memory for analysis; original trajectory bytes remain unchanged.']}


if __name__=='__main__':
    incoming,output=map(Path,sys.argv[1:]);p=json.loads(incoming.read_text());cfg=p['runtime']
    for name,version in cfg['packages'].items():
        if importlib.metadata.version(name)!=version:raise ValueError('Protein runtime version changed: '+name)
    try:
        result={'structure_pockets':pockets,'protein_dynamics':dynamics,'trajectory_analysis':analyze}[p['input']['tool']](p['input'],cfg,output.parent)
    except Exception as exc:result={'status':'failed','rows':[],'error_type':type(exc).__name__,'error':str(exc)[:1500]}
    result['versions']=cfg['packages'];output.write_text(json.dumps(result,ensure_ascii=False))
