"""Draw a 2D depiction of a structure that the research already retrieved.

Runs under the pinned science runtime because it needs RDKit. Input and output are files, like
the other science processes. This draws what the stored SMILES says; it does not standardise,
correct or choose a structure, and a string RDKit cannot parse is reported as unparsed rather
than replaced by a guess. A depiction is a drawing, not evidence about the physical sample.
"""
import json
import sys


# RDKit writes every stroke and fill into an inline `style` attribute. The page is served under
# `style-src 'self'`, which refuses inline styles, so the drawing arrived with its bonds invisible
# - a nearly blank box where a structure should be. Rather than weaken the policy for every page,
# the same declarations are rewritten as SVG presentation attributes, which carry no policy.
PRESENTATION = {'fill', 'fill-rule', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-linecap',
                'stroke-linejoin', 'stroke-opacity', 'stroke-dasharray', 'font-size',
                'font-family', 'font-style', 'font-weight', 'opacity'}


def _attributes(match):
    kept = []
    for declaration in match.group(1).split(';'):
        name, _, value = declaration.partition(':')
        name, value = name.strip(), value.strip()
        if name not in PRESENTATION or not value or '"' in value:
            continue
        # A presentation attribute takes a plain number; `2.0px` is a CSS length that older
        # renderers reject, so the unit RDKit writes is dropped here.
        if name in ('stroke-width', 'font-size') and value.endswith('px'):
            value = value[:-2]
        kept.append(f'{name}="{value}"')
    return ' '.join(kept)


def inline_styles_as_attributes(svg):
    """Move `style='…'` declarations onto the element as attributes. Appearance is unchanged."""
    import re
    return re.sub(r"style='([^']*)'", _attributes, svg)


def draw(smiles, width=280, height=200):
    from rdkit import Chem, RDLogger
    from rdkit.Chem import Descriptors, rdMolDescriptors
    from rdkit.Chem.Draw import rdMolDraw2D
    RDLogger.DisableLog('rdApp.*')
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return {'status': 'unparsed',
                'reason': 'RDKit could not read this SMILES; the stored string is unchanged.'}
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    options = drawer.drawOptions()
    options.clearBackground = False
    rdMolDraw2D.PrepareAndDrawMolecule(drawer, molecule)
    drawer.FinishDrawing()
    return {'status': 'drawn', 'svg': inline_styles_as_attributes(drawer.GetDrawingText()),
            'formula': rdMolDescriptors.CalcMolFormula(molecule),
            'exact_mass': round(Descriptors.ExactMolWt(molecule), 4),
            'average_mass': round(Descriptors.MolWt(molecule), 2),
            'heavy_atoms': molecule.GetNumHeavyAtoms(),
            'inchikey': Chem.MolToInchiKey(molecule) or None}


def main(request_path):
    request = json.loads(open(request_path, encoding='utf-8').read())
    results = {}
    for smiles in request['smiles']:
        try:
            results[smiles] = draw(smiles, request.get('width', 280), request.get('height', 200))
        except Exception as error:  # a single bad structure must not lose the rest
            results[smiles] = {'status': 'failed', 'reason': f'{type(error).__name__}: {error}'}
    from rdkit import rdBase
    with open(request['out'], 'w', encoding='utf-8') as handle:
        json.dump({'status': 'succeeded', 'rdkit_version': rdBase.rdkitVersion,
                   'results': results,
                   'meaning': 'Two-dimensional depiction of the stored SMILES. Not a measured '
                              'structure, a conformer, or identity verification of a sample.'},
                  handle, ensure_ascii=False)


if __name__ == '__main__':
    main(sys.argv[1])
