import matplotlib.pyplot as plt
import numpy as np
from numpy.polynomial import Chebyshev

# Función objetivo
f = np.tanh

# Aproximación Chebyshev grado 3 en [-1,1]
cheb = Chebyshev.fit(
    x=np.linspace(-1, 1, 2000),
    y=f(np.linspace(-1, 1, 2000)),
    deg=3,
    domain=[-1, 1]
)
poly = cheb.convert(kind=np.polynomial.Polynomial)

coeffs_poly = poly.coef

print("\nCoeficientes monomiales:")
for i, a in enumerate(coeffs_poly):
    print(f"a_{i} =", a, np.round(a,2))


x = np.linspace(-1, 1, 1000)

plt.plot(x, np.tanh(x), label="tanh")
plt.plot(x, poly(x), "--", label="Chebyshev deg 3")
plt.legend()
plt.grid()
plt.show()
