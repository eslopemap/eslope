#!/usr/bin/env python3

import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

name = sys.argv[1] if len(sys.argv) > 1 else 'oslo'

Ndegrees = 90
# structure expected by matplotlib.
# unlike the input, each color can have different "gradient segments"
cdict = {'red': [], 'green': [], 'blue': []}

src = 'gdaldem-slope-{}.clr'.format(name)
print (src, '->', name + '.png')

with open(src) as f:
    slope = 0
    for line in f:
        # nv is "no data" value, usually transparent
        if line.startswith('nv'): continue
        elems = list(map(float, line.strip().split()))
        if len(elems) < 5:  # transparency: opaque by default
            elems.append(255)
        slope, r, g, b, a = elems
        for cname, v in (('red', r), ('green', g), ('blue', b)):
            cdict[cname].append((slope / Ndegrees, v/255, v/255))
    if slope != 1:  # if missing, fill in up to 90° / last element
        for cname in cdict:
            _, before, after = cdict[cname][-1]
            cdict[cname].append((1, before, after))

# from pprint import pprint; pprint(cdict)

# import hsluv
# for i in range(len(cdict['red'])):
#     r, g, b = cdict['red'][i], cdict['green'][i], cdict['blue'][i]
#     print(r, g, b, hsluv.rgb_to_hsluv((r, g, b)))

themap = LinearSegmentedColormap(name, segmentdata=cdict, N=Ndegrees)

gradient = np.linspace(0, 1,  Ndegrees)
gradient = np.vstack((gradient, gradient))

fig, ax = plt.subplots(figsize=(10,2))

ax.imshow(gradient, aspect='auto', cmap=themap)
ax.set_title(name, fontsize=14)
ax.set_yticks([])
ax.set_xticks([10,20,30,35,40,45,50,55,60])
ax.set_xlim([0,60])

fig.savefig(name + '.png')

