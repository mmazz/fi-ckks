# Toy CKKS with N = 8 and n = 2 slots (gap 2) to follow a bit flip in a non-aligned
# coefficient of c0 through a ciphertext-ciphertext multiplication, the relinearization,
# the rescaling, the decryption and the decoding. HEAAN-like: power-of-two moduli,
# rescaling and key switching by floor division. Exact integers throughout.
import json
import random
import cmath
import math

N, n = 8, 2
GAP = N // (2 * n)
LOG_DELTA, LOG_Q, LOG_P = 10, 40, 40          # scale 2^10, modulus 2^40, special modulus 2^40
DELTA, q, P = 1 << LOG_DELTA, 1 << LOG_Q, 1 << LOG_P
H = 4
SIGMA = 3.2
import sys
rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 3)   # seed 3 = thesis appendix


def center(a, m):
    a %= m
    return a - m if a >= m // 2 else a


def polymul(a, b, m=None):
    """Negacyclic product in Z[X]/(X^N + 1), optionally reduced mod m (centered)."""
    out = [0] * N
    for i in range(N):
        if a[i] == 0:
            continue
        for j in range(N):
            k = i + j
            if k < N:
                out[k] += a[i] * b[j]
            else:
                out[k - N] -= a[i] * b[j]
    return [center(x, m) for x in out] if m else out


def add(a, b, m=None):
    out = [x + y for x, y in zip(a, b)]
    return [center(x, m) for x in out] if m else out


def gauss():
    return [round(rng.gauss(0, SIGMA)) for _ in range(N)]


def uniform(m):
    return [center(rng.randrange(m), m) for _ in range(N)]


# --- encoding: m(X) = m~(X^GAP), m~ in Z[X]/(X^(2n)+1), slots at the roots zeta^(5^k)
NP = 2 * n
ZETA = cmath.exp(1j * math.pi / NP)
ROOTS = [ZETA ** (5 ** k) for k in range(n)]


def encode(z, scale):
    # Solve m~(r) = z_k for the n slot roots and their conjugates (real coefficients).
    pts = ROOTS + [r.conjugate() for r in ROOTS]
    vals = list(z) + [complex(v).conjugate() for v in z]
    # m~_j = (1 / NP) * sum over the 2n points of val * conj(pt)^j (orthogonality)
    mt = [sum(v * (p.conjugate() ** j) for p, v in zip(pts, vals)).real / NP for j in range(NP)]
    m = [0] * N
    for j in range(NP):
        m[j * GAP] = round(scale * mt[j])
    return m


def decode(m, scale):
    """Read only the aligned coefficients, as HEAAN does, and evaluate at the slot roots."""
    mt = [m[j * GAP] for j in range(NP)]
    return [sum(c * (r ** j) for j, c in enumerate(mt)).real / scale for r in ROOTS]


# --- keys
s = [0] * N
for i in rng.sample(range(N), H):
    s[i] = rng.choice([-1, 1])
s2 = polymul(s, s)
ak = uniform(q * P)
ek = gauss()
k0 = add(add(polymul([-x for x in ak], s, q * P), ek, q * P), [P * x for x in s2], q * P)
k1 = ak


def encrypt(m):
    a = uniform(q)
    e = gauss()
    c0 = add(add(polymul([-x for x in a], s, q), m, q), e, q)
    return [c0, a], e


def decrypt(c, m):
    return add(c[0], polymul(c[1], s, m), m)


def tensor(c, cp, m):
    d0 = polymul(c[0], cp[0], m)
    d1 = add(polymul(c[0], cp[1], m), polymul(c[1], cp[0], m), m)
    d2 = polymul(c[1], cp[1], m)
    return d0, d1, d2


def relin(d0, d1, d2, m):
    t0 = [x // P for x in polymul(d2, k0, m * P)]   # floor division, as HEAAN's shift
    t1 = [x // P for x in polymul(d2, k1, m * P)]
    return [add(d0, t0, m), add(d1, t1, m)]


def rescale(c, m):
    return [[center(x, m) // DELTA for x in comp] for comp in c], m // DELTA


def l2_rel(y, z):
    num = math.sqrt(sum((a - b) ** 2 for a, b in zip(y, z)))
    den = math.sqrt(sum(b ** 2 for b in z))
    return num / den


# --- inputs
x1 = [0.70, -0.40]
x2 = [0.50, 0.90]
m1, m2 = encode(x1, DELTA), encode(x2, DELTA)
c1, e1 = encrypt(m1)
c2, e2 = encrypt(m2)


def pipeline(fault=None, mul=True):
    """fault = (component, coefficient, bit). Returns every intermediate value."""
    c = [list(c1[0]), list(c1[1])]
    if fault:
        comp, coef, bit = fault
        v = c[comp][coef] % q
        c[comp][coef] = center(v ^ (1 << bit), q)
    out = {"c": c, "phi": decrypt(c, q)}
    if not mul:
        out["slots"] = decode(out["phi"], DELTA)
        return out
    d0, d1, d2 = tensor(c, c2, q)
    out["d"] = [d0, d1, d2]
    out["phi_tensor"] = add(add(d0, polymul(d1, s, q), q), polymul(d2, s2, q), q)
    cr = relin(d0, d1, d2, q)
    out["relin"] = cr
    out["phi_relin"] = decrypt(cr, q)
    cs, q1 = rescale(cr, q)
    out["rescaled"] = cs
    out["phi_rescaled"] = decrypt(cs, q1)
    out["slots"] = decode(out["phi_rescaled"], DELTA)
    return out


BIT, POS = 12, 3
clean = pipeline()
faulty = pipeline((0, POS, BIT))
clean_nomul = pipeline(mul=False)
faulty_nomul = pipeline((0, POS, BIT), mul=False)
aligned = pipeline((0, 2, BIT))
c1_nomul = pipeline((1, POS, BIT), mul=False)
c1_mul = pipeline((1, POS, BIT))


def diff(a, b, m=None):
    return [center(x - y, m) if m else x - y for x, y in zip(a, b)]


E_sign = (faulty["c"][0][POS] - clean["c"][0][POS]) // (1 << BIT)
E = [0] * N
E[POS] = E_sign * (1 << BIT)
# exact split of the change of the decrypted product: E*m2 and E*e2
Em2 = polymul(E, m2)
Ee2 = polymul(E, e2)

data = {
    "params": {"N": N, "n": n, "gap": GAP, "logDelta": LOG_DELTA, "logq": LOG_Q, "logP": LOG_P,
               "h": H, "sigma": SIGMA, "bit": BIT, "pos": POS},
    "x1": x1, "x2": x2, "expected": [a * b for a, b in zip(x1, x2)],
    "s": s, "m1": m1, "m2": m2, "e1": e1, "e2": e2,
    "c1": c1, "c2": c2,
    "phi1": clean_nomul["phi"],
    "E": E, "E_sign": E_sign,
    "slots_clean_nomul": clean_nomul["slots"], "slots_faulty_nomul": faulty_nomul["slots"],
    "d_clean": clean["d"], "d_diff": [diff(a, b, q) for a, b in zip(faulty["d"], clean["d"])],
    "phi_tensor_diff": diff(faulty["phi_tensor"], clean["phi_tensor"], q),
    "relin_diff": [diff(a, b, q) for a, b in zip(faulty["relin"], clean["relin"])],
    "phi_relin_diff": diff(faulty["phi_relin"], clean["phi_relin"], q),
    "Em2": Em2, "Ee2": Ee2,
    "phi_rescaled_clean": clean["phi_rescaled"], "phi_rescaled_faulty": faulty["phi_rescaled"],
    "phi_rescaled_diff": diff(faulty["phi_rescaled"], clean["phi_rescaled"]),
    "slots_clean": clean["slots"], "slots_faulty": faulty["slots"],
    "el2": {
        "nomul_c0_nonaligned": l2_rel(faulty_nomul["slots"], clean_nomul["slots"]),
        "mul_c0_nonaligned": l2_rel(faulty["slots"], clean["slots"]),
        "mul_c0_aligned": l2_rel(aligned["slots"], clean["slots"]),
        "nomul_c1_nonaligned": l2_rel(c1_nomul["slots"], clean_nomul["slots"]),
        "mul_c1_nonaligned": l2_rel(c1_mul["slots"], clean["slots"]),
    },
    "slots_aligned": aligned["slots"], "slots_c1_nomul": c1_nomul["slots"],
}
# explicit cancellation when decrypting the change of the product: E*c0' + E*c1'*s = E*(m' + e')
data["cancel"] = {
    "Ec0p": polymul(E, c2[0], q),
    "Ec1ps": polymul(polymul(E, c2[1], q), s, q),
}
data["cancel"]["sum"] = add(data["cancel"]["Ec0p"], data["cancel"]["Ec1ps"], q)
assert data["cancel"]["sum"] == data["phi_tensor_diff"]
json.dump(data, open("toy.json", "w"), indent=1)
for k in ["s", "m1", "m2", "e1", "e2", "phi1", "E", "phi_tensor_diff", "phi_relin_diff", "Em2", "Ee2",
          "phi_rescaled_clean", "phi_rescaled_diff", "slots_clean", "slots_faulty", "expected",
          "slots_clean_nomul", "slots_faulty_nomul", "el2"]:
    print(k, data[k])
print("d_diff", data["d_diff"])
print("relin_diff", data["relin_diff"])
# check: the change of the decrypted tensor equals E*phi2 mod q, and phi2 = m2 + e2
phi2 = decrypt(c2, q)
print("phi2 == m2+e2:", phi2 == add(m2, e2), " tensor diff == E*(m2+e2):",
      data["phi_tensor_diff"] == polymul(E, add(m2, e2), q))
