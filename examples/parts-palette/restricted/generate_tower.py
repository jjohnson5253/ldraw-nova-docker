"""Generate the editable inventory-constrained Ember Garden lookout plan."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
sections = []
def place(id, ref, colour, x, y, z, purpose, yaw=None):
    p = dict(id=id, ref=f"{ref}.dat", colour=colour, at=[x, y, z], purpose=purpose)
    if yaw is not None:
        p['yaw'] = yaw
    return p

def section(name, description, steps):
    sections.append(dict(name=name, description=description, steps=steps))

# Two long slabs make a square, while crossing plates stitch their meeting seam.
base = [[place(f'ground-{z}', '3035', 72, 0, 0, z, 'ground slab') for z in (-40, 40)],
        [place(f'ground-stitch-{x}', '3020', 0, x, -8, 0, 'bridge both ground slabs') for x in (-40, 40)]]
section('ember-ground.ldr', 'Square grey footing with bonded center seam', base)

lower = []
for tier, y in enumerate((-24, -48, -72)):
    lower.append([place(f'lower-{tier}-{x}-{z}', '3005', 4, x, y, z,
                        'load-bearing red corner pier; leave doorway open')
                  for z in (-50, 50) for x in (-50, 50)])
section('ember-lower-piers.ldr', 'Four open portal supports', lower)

deck = [[place(f'deck-slab-{z}', '3035', 72, 0, 0, z, 'raised square observation floor') for z in (-40, 40)],
        [place(f'deck-stitch-{x}', '3020', 0, x, -8, 0, 'lock the two halves of the deck') for x in (-40, 40)]]
section('ember-deck.ldr', 'Bonded raised observation platform', deck)

upper = []
for tier, y in enumerate((-24, -48, -72)):
    upper.append([place(f'upper-{tier}-{x}-{z}', '3005', 4, x, y, z,
                        'open viewing level corner column')
                  for z in (-50, 50) for x in (-50, 50)])
section('ember-upper-piers.ldr', 'Four red open-air viewing posts', upper)

roof = [[place(f'roof-long-{x}-{z}', '3020', 0, x, 0, z, 'roof underside plate')
         for z in (-60, -20, 20, 60) for x in (-40, 40)],
        [place(f'roof-cross-{x}-{z}', '3020', 0, x, -8, z,
               'cross-bond roof plate seams', 90)
         for x in (-60, -20, 20, 60) for z in (-40, 40)],
        [place(f'roof-tile-{x}-{z}', '3068b', 0, x, -16, z,
               'alternating quiet black roof tile')
         for x in (-60, -20, 20, 60) for z in (-60, -20, 20, 60)
         if ((x + 60)//40 + (z + 60)//40) % 2 == 0]]
section('ember-canopy.ldr', 'Cross-bonded broad black pavilion canopy', roof)

main = dict(name='ember-garden-lookout.ldr',
            description='Ember Garden Lookout - open red tower with black canopy',
            steps=[
                [dict(id='footing', ref='ember-ground.ldr', colour=16, at=[0,0,0], purpose='ground foundation')],
                [dict(id='portal', ref='ember-lower-piers.ldr', colour=16, at=[0,0,0], purpose='four supports leaving front doorway unobstructed')],
                [dict(id='deck', ref='ember-deck.ldr', colour=16, at=[0,-80,0], purpose='raised viewing platform seated on the lower posts')],
                [dict(id='posts', ref='ember-upper-piers.ldr', colour=16, at=[0,-80,0], purpose='four viewing posts')],
                [dict(id='canopy', ref='ember-canopy.ldr', colour=16, at=[0,-160,0], purpose='sheltering bonded black roof')],
            ])
plan = dict(version=1, author='OpenAI for this workspace', sections=[main, *sections])
(OUT/'ember-garden-lookout.plan.json').write_text(json.dumps(plan, indent=2)+'\n')
print('placements', sum(len(step) for s in sections for step in s['steps']))
