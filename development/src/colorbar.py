#!/usr/bin/env python3

import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

name = sys.argv[1] if len(sys.argv) > 1 else 'oslo'

Ndegrees = 90
cdict = {'red': [], 'green': [], 'blue': []}

with open('gdaldem-slope-{}.clr'.format(name)) as f:
    slope = 0
    for line in f:
        elems = list(map(float, line.strip().split()))
        if len(elems) < 5:
            elems.append(255)
        slope, r, g, b, a = elems
        for k, v in (('red', r), ('green', g), ('blue', b)):
            cdict[k].append((slope / Ndegrees, v/255, v/255))
    if slope != 1:  # 90°
        for k in cdict:
            _, before, after = cdict[k][-1]
            cdict[k].append((1, before, after))

# from pprint import pprint; pprint(cdict)

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

