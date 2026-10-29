"""Capture graph at the original Meeko author boundary; fixed preparation flags."""
import importlib.metadata
import json
from pathlib import Path
import sys
from meeko import Polymer
from meeko.cli.mk_prepare_receptor import main
from evida.receptor_graph import export_prepared_graph


def run(work):
    if importlib.metadata.version('meeko')!='0.7.1':
        raise ValueError('Graph capture boundary is tested only for pinned Meeko0.7.1.')
    work=Path(work).resolve();captured={}
    original_build=Polymer._build_padded_mols;original_pdb=Polymer.to_pdb
    def build(monomers,bonds,padders):
        if 'links'in captured:captured['capture_error']='Unexpected repeated author graph preparation.'
        captured['links']={key:list(value)for key,value in bonds.items()}
        return original_build(monomers,bonds,padders)
    def to_pdb(polymer,*args,**kwargs):
        value=original_pdb(polymer,*args,**kwargs);captured['polymer']=polymer
        return value
    oldargv=sys.argv
    try:
        Polymer._build_padded_mols=staticmethod(build);Polymer.to_pdb=to_pdb
        sys.argv=['mk_prepare_receptor.py','--read_pdb',str(work/'receptor-source.pdb'),'-o',str(work/'receptor'),'-p','--write_pdb',str(work/'receptor-prepared.pdb')]
        main()
        try:
            if set(captured)!={'links','polymer'}:raise ValueError('Author graph capture incomplete or repeated.')
            graph=export_prepared_graph(captured['polymer'],captured['links'],(work/'receptor-prepared.pdb').read_text())
            graph['versions']={p:importlib.metadata.version(p)for p in ('meeko','rdkit','gemmi')}
            temporary=work/'receptor-graph.tmp'
            temporary.write_text(json.dumps(graph,separators=(',',':'),allow_nan=False)+'\n')
            temporary.replace(work/'receptor-graph.json')
        except Exception as error:
            # Optional graph export must not reinterpret a completed native preparation.
            # Retain a visible unavailable record; contact analysis cannot use it as a graph.
            (work/'receptor-graph-unavailable.json').write_text(json.dumps({'status':'unavailable',
                'error_type':type(error).__name__,'error':str(error)[:600],
                'native_preparation_preserved':True,'bond_guessing_fallback':False})+'\n')
    finally:
        Polymer._build_padded_mols=staticmethod(original_build);Polymer.to_pdb=original_pdb;sys.argv=oldargv

if __name__=='__main__':run(sys.argv[1])
