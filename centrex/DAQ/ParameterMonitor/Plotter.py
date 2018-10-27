import numpy as np
import time
import matplotlib.pyplot as plt
import matplotlib.animation as animation

temp_dir = "C:/Users/CENTREX/Documents/data/temp_run_dir"
ig_f = open(temp_dir+"/beam_source/pressure/IG.csv", 'r+', newline='\n')
ig_f.seek(0,2) # go to the end of file

x_len = 100
fig = plt.figure()
ax = fig.add_subplot(1, 1, 1)
xs = range(x_len)
ys = [0] * x_len
ax.set_ylim([1e-9,1e-6])
line, = ax.semilogy(xs, ys)
plt.xlabel('time')
plt.ylabel('IG pressure [torr]')

def animate(i, ys):
    where = ig_f.tell()
    row = ig_f.readline()
    if not row:
        time.sleep(0.1)
        ig_f.seek(where)
    else:
        ys.append(float(row.split(',')[1]))
        print(ys[-1])
    ys = ys[-x_len:]
    line.set_ydata(ys)
    return line,

ani = animation.FuncAnimation(fig,
    animate,
    fargs=(ys,),
    interval=100,
    blit=True)

plt.show()
