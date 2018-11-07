import numpy as np
import matplotlib.pyplot as plt

energies = np.loadtxt("energies.csv", delimiter=',')
Ex = np.linspace(0,70,100)

plt.plot(Ex, energies[:, 4:16])
plt.show()
