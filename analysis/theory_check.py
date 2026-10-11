#!/usr/bin/env python3
"""Numerical check of the analytical fault model (thesis, analytical chapter).

A toy HEAAN-like CKKS with exact integers: power-of-two modulus q = 2^logq, key
switching modulus Q = 2^logQ, Karatsuba multiplication and floor shifts exactly as
HEAAN-PRNG-Control/src/Scheme.cpp (multBitFlip / multBitFlipAsplos), sparse decoding
as Scheme::decode (reads only the coefficients multiple of the gap).

Every check prints PASS/FAIL and the numbers behind it.
"""
import random, cmath, math
import numpy as np

random.seed(7)
N, LOGQ_KS, LOGQ, LOGD, H = 64, 60, 60, 30, 4
Q_KS, q, D = 1 << LOGQ_KS, 1 << LOGQ, 1 << LOGD


# ---------------------------------------------------------------- ring helpers
def mul(a, b, mod):
    """Negacyclic product mod (X^N + 1, mod), coefficients in [0, mod)."""
    r = [0] * N
    for i, ai in enumerate(a):
        if ai == 0:
            continue
        for j, bj in enumerate(b):
            if bj == 0:
                continue
            k = i + j
            if k < N:
                r[k] += ai * bj
            else:
                r[k - N] -= ai * bj
    return [x % mod for x in r]


def add(a, b, mod):
    return [(x + y) % mod for x, y in zip(a, b)]


def sub(a, b, mod):
    return [(x - y) % mod for x, y in zip(a, b)]


def shr(a, bits):
    return [x >> bits for x in a]          # NTL RightShift on [0, mod): floor


def centered(a, mod):
    return [x - mod if x >= mod // 2 else x for x in a]


def mono(e, i):
    p = [0] * N
    p[i] = e
    return p


def flip(p, i, b):
    """Bit flip of coefficient i, bit b, in place. Returns the signed change."""
    old = p[i]
    p[i] ^= (1 << b)
    return p[i] - old


# ---------------------------------------------------------------- keys, encryption
def sample_hwt(h):
    s = [0] * N
    for i in random.sample(range(N), h):
        s[i] = random.choice([1, -1])
    return s


s = sample_hwt(H)
s_mod = lambda mod: [x % mod for x in s]
k1 = [random.randrange(Q_KS * Q_KS) for _ in range(N)]                    # key.ax
e_evk = [round(random.gauss(0, 3.2)) for _ in range(N)]
ss = mul(s_mod(Q_KS * Q_KS), s_mod(Q_KS * Q_KS), Q_KS * Q_KS)
k0 = sub(add([x * Q_KS for x in ss], [x % (Q_KS * Q_KS) for x in e_evk], Q_KS * Q_KS),
         mul(s_mod(Q_KS * Q_KS), k1, Q_KS * Q_KS), Q_KS * Q_KS)           # key.bx


def phase(ax, bx, mod):
    """phi(c) = bx + ax * s mod `mod` (HEAAN: c0 = bx, c1 = ax), centered."""
    return centered(add(bx, mul(ax, s_mod(mod), mod), mod), mod)


# Slots: n complex values, gap = N/(2n). HEAAN slot k <-> zeta_k = exp(2 pi i 5^k / 4n).
def slot_matrix(n):
    return np.array([[cmath.exp(2j * math.pi * pow(5, k, 4 * n) * r / (4 * n))
                      for r in range(n)] for k in range(n)])


def encode(z, n, scale):
    gap = N // (2 * n)
    u = np.linalg.solve(slot_matrix(n), np.array(z, dtype=complex))
    m = [0] * N
    for r in range(n):
        m[r * gap] = int(round(u[r].real * scale))
        m[N // 2 + r * gap] = int(round(u[r].imag * scale))
    return m


def decode(phi, n, scale):
    """Scheme::decode: u_r = (phi[r gap] + i phi[N/2 + r gap]) / scale, slots = V u."""
    gap = N // (2 * n)
    u = np.array([complex(phi[r * gap], phi[N // 2 + r * gap]) / scale for r in range(n)])
    return slot_matrix(n) @ u


def encrypt(m, mod):
    ax = [random.randrange(mod) for _ in range(N)]
    e = [round(random.gauss(0, 3.2)) for _ in range(N)]
    bx = sub(add([x % mod for x in m], [x % mod for x in e], mod), mul(ax, s_mod(mod), mod), mod)
    return ax, bx


def report(name, ok, detail):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# ================================================================ T1 one-bit law
def t1():
    for n in (32, 8):
        gap = N // (2 * n)
        z = [random.uniform(-1, 1) for _ in range(n)]
        rms = math.sqrt(sum(x * x for x in z) / n)
        worst = 0.0
        special = {}
        for i in range(N):
            for b in (35, 45):
                E = 1 << b
                err = decode(mono(E, i), n, D).real          # decoding is linear
                el2 = np.linalg.norm(err) / (math.sqrt(n) * rms)
                pred = E / D / (math.sqrt(2) * rms)
                if i % gap:
                    special.setdefault("non-aligned", []).append(el2)
                elif i == 0:
                    special.setdefault("i=0", []).append(el2 / pred)
                elif i == N // 2:
                    special.setdefault("i=N/2", []).append(el2)
                else:
                    worst = max(worst, abs(el2 / pred - 1))
        report(f"T1 one-bit law, n={n}",
               worst < 1e-9 and max(special["i=N/2"]) == 0 and
               (n == N // 2 or max(special["non-aligned"]) == 0) and
               abs(np.mean(special["i=0"]) - math.sqrt(2)) < 1e-9,
               f"max |ratio-1| aligned = {worst:.1e}; i=0 ratio = {np.mean(special['i=0']):.4f}; "
               f"i=N/2 max = {max(special['i=N/2'])}; non-aligned max = "
               f"{max(special.get('non-aligned', [0]))}")


# ================================================================ T2 c1 fault: E X^i s
def t2():
    n = 32
    z = [random.uniform(-1, 1) for _ in range(n)]
    rms = math.sqrt(sum(x * x for x in z) / n)
    ratios = []
    for i in range(N):
        E = 1 << 40
        d = mul(mono(E, i), s_mod(q), q)
        err = decode(centered(d, q), n, D).real
        c0 = decode(mono(E, 1), n, D).real
        ratios.append(np.linalg.norm(err) / np.linalg.norm(c0))
        nz = sum(1 for x in centered(d, q) if x)
    ratios = np.array(ratios)
    report("T2 c1 fault, full packing", abs(np.median(ratios) - math.sqrt(H)) < 0.2,
           f"E X^i s has {nz} non-zero coefficients (= h = {H}, not N); "
           f"||err_c1|| / ||err_c0||: median {np.median(ratios):.3f} (sqrt h = {math.sqrt(H):.3f}), "
           f"p10 {np.percentile(ratios, 10):.2f}, p90 {np.percentile(ratios, 90):.2f}")
    # Sparse packing: which non-aligned classes reach the decoder through s
    for n in (8,):
        gap = N // (2 * n)
        supp = [u for u in range(N) if s[u]]
        reach = {r: sum(1 for u in supp if (r + u) % gap == 0) for r in range(1, gap)}
        ok, half = True, []
        for i in range(N):
            if i % gap == 0:
                continue
            d = centered(mul(mono(1 << 45, i), s_mod(q), q), q)
            land = [k for k, x in enumerate(d) if x and k % gap == 0 and k != N // 2]
            err = decode(d, n, D).real
            vis = bool(np.linalg.norm(err) > 1e-6 * (1 << 15))
            ok &= vis == bool(land)
            if vis:
                half.append(np.mean(np.abs(err) > 1e-6 * np.abs(err).max()))
        report(f"T2 c1 fault, gap {gap}: visible iff i + supp(s) hits an aligned position != N/2", ok,
               f"supp(s) mod gap = {sorted(u % gap for u in supp)}; landings per class r = {reach}; "
               f"fraction of slots with non-zero error: {sorted(set(np.round(half, 3)))}")


# ================================================================ T3 multiplication
def he_mult(c1, c2, logq, step=None, coeff=0, bit=0, persistent=False):
    """Scheme::multBitFlip (restore after the marked read) or multBitFlipAsplos
    (persistent). Returns (ax, bx, E) of the output and the signed change E."""
    qq = 1 << logq
    qQ = 1 << (logq + LOGQ_KS)
    a1, b1 = list(c1[0]), list(c1[1])
    a2, b2 = list(c2[0]), list(c2[1])
    k_ax, k_bx = [x % qQ for x in k1], [x % qQ for x in k0]
    E = [0]

    def f(st, p):
        if step == st:
            E[0] = flip(p, coeff, bit)

    def r(st, p):                                         # restoreIfStep
        if step == st and not persistent:
            flip(p, coeff, bit)

    f(0, a1); f(1, b1); axbx1 = add(a1, b1, qq); r(0, a1); r(1, b1)
    f(2, a2); f(3, b2); axbx2 = add(a2, b2, qq); r(2, a2); r(3, b2)
    f(4, axbx1); f(5, axbx2); axbx1 = mul(axbx1, axbx2, qq)
    f(6, a1); f(7, a2); axax = mul(a1, a2, qq); r(6, a1); r(7, a2)
    f(8, b1); f(9, b2); bxbx = mul(b1, b2, qq); r(8, b1); r(9, b2)
    f(10, axax); f(11, k_ax); axmult = mul(axax, k_ax, qQ); r(10, axax)
    f(12, axax); f(13, k_bx); bxmult = mul(axax, k_bx, qQ); r(12, axax)
    f(14, axmult); axmult = shr(axmult, LOGQ_KS)
    f(15, bxmult); bxmult = shr(bxmult, LOGQ_KS)
    axmult = [x % qq for x in axmult]; bxmult = [x % qq for x in bxmult]
    f(16, axmult); f(17, axbx1); axmult = add(axmult, axbx1, qq)
    f(18, axmult); f(19, bxbx); axmult = sub(axmult, bxbx, qq); r(19, bxbx)
    f(20, axmult); f(21, axax); axmult = sub(axmult, axax, qq)
    f(22, bxmult); f(23, bxbx); bxmult = add(bxmult, bxbx, qq)
    f(24, axmult); f(25, bxmult)
    return (axmult, bxmult), E[0], dict(t1=add(c1[0], c1[1], qq), t2=add(c2[0], c2[1], qq),
                                         d2=mul(c1[0], c2[0], qq))


def t3():
    n = 8
    logq = LOGQ
    z1 = [random.uniform(-1, 1) for _ in range(n)]
    z2 = [random.uniform(-1, 1) for _ in range(n)]
    c1 = encrypt(encode(z1, n, D), q)
    c2 = encrypt(encode(z2, n, D), q)
    clean, _, aux = he_mult(c1, c2, logq)
    phi_clean = phase(*clean, q)
    S = s_mod(q)
    one_minus_s = sub([1] + [0] * (N - 1), S, q)
    s_minus_1 = sub(S, [1] + [0] * (N - 1), q)
    phi2 = phase(c2[0], c2[1], q)
    qQ = 1 << (logq + LOGQ_KS)

    def m_(a, b, mod=q):
        return mul([x % mod for x in a], [x % mod for x in b], mod)

    # Predicted phase change for each step, as a function of the signed change E (monomial).
    def predicted(step, Ep):
        if step in (0, 1, 4):  return m_(m_(Ep, aux["t2"]), S)                 # E t2 s
        if step in (2, 3, 5):  return m_(m_(Ep, aux["t1"]), S)                 # E t1 s
        if step == 6:          return m_(m_(Ep, c2[0]), m_(S, s_minus_1))      # E c1' s (s-1)
        if step == 7:          return m_(m_(Ep, c1[0]), m_(S, s_minus_1))
        if step == 8:          return m_(m_(Ep, c2[1]), one_minus_s)           # E c0' (1-s)
        if step == 9:          return m_(m_(Ep, c1[1]), one_minus_s)
        if step == 10:   # floor(E k1 / Q) s
            return m_([x % q for x in shr(mul([x % qQ for x in Ep], [x % qQ for x in k1], qQ), LOGQ_KS)], S)
        if step == 11:
            return m_([x % q for x in shr(mul(aux["d2"], [x % qQ for x in Ep], qQ), LOGQ_KS)], S)
        if step == 12:
            return [x % q for x in shr(mul([x % qQ for x in Ep], [x % qQ for x in k0], qQ), LOGQ_KS)]
        if step == 13:
            return [x % q for x in shr(mul(aux["d2"], [x % qQ for x in Ep], qQ), LOGQ_KS)]
        if step in (16, 17, 18, 20, 24): return m_(Ep, S)                      # E s
        if step in (19, 21):   return m_([(-x) % q for x in Ep], S)            # -E s
        if step in (22, 23, 25): return [x % q for x in Ep]                    # E
        return None

    print("T3 multiplication, read-fault model (restore after the marked read):")
    rows = []
    for step in range(26):
        for bit in (0, 20, 45):
            coeff = 4 if step not in (14, 15) else 4
            b = bit if step not in (10, 11, 12, 13, 14, 15) else bit + (60 if step in (14, 15) else 0)
            out, E, _ = he_mult(c1, c2, logq, step=step, coeff=coeff, bit=b)
            dphi = [(x - y) for x, y in zip(phase(*out, q), phi_clean)]
            dphi = centered([x % q for x in dphi], q)
            pred = predicted(step, mono(E, coeff))
            if pred is None:
                resid = None
            else:
                resid = max(abs(x) for x in centered(sub([x % q for x in dphi], pred, q), q))
            size = max(abs(x) for x in dphi)
            rows.append((step, b, size, resid))
    ks_noise = 2 * (q // Q_KS) * sum(abs(x) for x in e_evk) + 2 * (1 + H)
    worst = max(r[3] for r in rows if r[3] is not None and r[0] not in (10, 12))
    worst_ks = max(r[3] for r in rows if r[0] in (10, 12))
    per = {}
    for r in rows:
        if r[3] is not None:
            per[r[0]] = max(per.get(r[0], 0), r[3])
    print("    residual per step:", per)
    report("T3 phase change = formula (steps 0-9, 11, 13, 16-25)", worst <= ks_noise,
           f"max |dphi - formula| = {worst} <= KS noise bound {ks_noise}")
    report("T3 KS read faults 10, 12 = formula", worst_ks <= 2 * (1 + H),
           f"max |dphi - formula| = {worst_ks}")
    destroy = [r for r in rows if r[0] in range(0, 13) and r[0] not in (11,)]
    frac = [r[2] / (q / 2) for r in destroy]
    report("T3 steps 0-10, 12 give |dphi| ~ q at any bit", min(frac) > 0.25,
           f"max_l |dphi_l| / (q/2) over bits 0, 20, 45: min {min(frac):.2f}")
    s14 = [r for r in rows if r[0] == 14]
    print("    step 14 (before >> logQ), bit -> max|dphi|:",
          {r[1]: r[2] for r in s14}, "(expected ~2^(bit - logQ) * |s|)")

    print("T3 multiplication, persistent-fault model (multBitFlipAsplos):")
    for step, name, pred_fn in [
        (0, "c1 persistent -> E s phi'", lambda Ep: m_(m_(Ep, S), [x % q for x in phi2])),
        (1, "c0 persistent -> E phi'", lambda Ep: m_(Ep, [x % q for x in phi2])),
        (10, "d2 persistent -> E s (s-1)", lambda Ep: m_(m_(Ep, S), s_minus_1)),
    ]:
        worst, size = 0, 0
        for bit in (0, 20, 45):
            out, E, _ = he_mult(c1, c2, logq, step=step, coeff=4, bit=bit, persistent=True)
            dphi = centered([(x - y) % q for x, y in zip(phase(*out, q), phi_clean)], q)
            resid = max(abs(x) for x in centered(sub([x % q for x in dphi], pred_fn(mono(E, 4)), q), q))
            worst = max(worst, resid)
            size = max(size, max(abs(x) for x in dphi))
        report(f"T3 {name}", worst <= 2 * (q // Q_KS) * sum(abs(x) for x in e_evk) + 2 * (1 + H),
               f"max |dphi - formula| = {worst}; max |dphi| = 2^{math.log2(size):.1f}")


# ================================================================ T4 classes mod gap
def t4():
    gap = 4
    sparse = [0] * N
    for r in range(0, N, gap):
        sparse[r] = random.randrange(1, 1000)
    dense = [random.randrange(1, 1000) for _ in range(N)]
    for i in (1, 2, 3):
        E = mono(1 << 20, i)
        cls = lambda p: sorted({k % gap for k, x in enumerate(centered(p, q)) if x})
        a = cls(mul(E, sparse, q))
        b = cls(mul(E, dense, q))
        # automorphism X -> X^5 (rotation): index i -> 5 i mod 2N
        j = (5 * i) % (2 * N)
        report(f"T4 class of i={i}", a == [i % gap] and 0 in b and (j % N) % gap == i % gap,
               f"x sparse plaintext -> classes {a}; x dense noise -> {b}; X->X^5 maps class "
               f"{i % gap} to {(j % N) % gap}")


# ================================================================ T5 divisibility
def t5():
    ok = True
    for _ in range(2000):
        x = random.randrange(q)
        b = random.randrange(LOGD, LOGQ)
        E = (1 << b) * random.choice([1, -1])
        lhs = ((x + E) % q >> LOGD) - (x >> LOGD)
        if (lhs - (E >> LOGD)) % (q >> LOGD) != 0:
            ok = False
    report("T5 floor rescale is exact on multiples of Delta", ok,
           "floor((x + 2^b) / Delta) - floor(x / Delta) = 2^(b - logDelta) for b >= logDelta")
    # c0 fault through a ct x ct product keeps divisibility; KS rounding breaks it
    n = 8
    c1 = encrypt(encode([random.uniform(-1, 1) for _ in range(n)], n, D), q)
    c2 = encrypt(encode([random.uniform(-1, 1) for _ in range(n)], n, D), q)
    clean, _, _ = he_mult(c1, c2, LOGQ)
    for st, label in ((1, "c0 (no key switching on the fault)"), (0, "c1 (goes through KS)")):
        out, E, _ = he_mult(c1, c2, LOGQ, step=st, coeff=4, bit=40, persistent=True)
        dax = centered([(x - y) % q for x, y in zip(out[0], clean[0])], q)
        dbx = centered([(x - y) % q for x, y in zip(out[1], clean[1])], q)
        div = all(x % (1 << 40) == 0 for x in dax + dbx)
        print(f"    fault at bit 40 in {label}: output change divisible by 2^40: {div}")


# ================================================================ T6 RNS and NTT
def is_prime(n):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2; r += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def ntt_primes(bits, count, avoid=()):
    out, c = [], (1 << bits) - 2 * N + 1
    while len(out) < count:
        if is_prime(c) and c not in avoid:
            out.append(c)
        c -= 2 * N
    return out


def t6():
    primes = ntt_primes(60, 1) + ntt_primes(30, 3)
    Qr = math.prod(primes)
    print(f"T6 RNS: limbs {[p.bit_length() for p in primes]} bits, log2 Q = {math.log2(Qr):.1f}")
    for k, qk in enumerate(primes):
        Qk = Qr // qk
        inv = pow(Qk, -1, qk)
        mags, low = [], 0
        for j in range(64):
            m = (pow(2, j, qk) * inv) % qk
            m = m - qk if m > qk // 2 else m
            d = abs(m) * Qk
            mags.append(d / Qr)
            low = min(low, d) if low else d
        report(f"T6 RNS limb {k}", min(mags) * Qr >= Qk,
               f"|delta| / Q over bits 0..63: min {min(mags):.2e} (bound Q_k/Q = {Qk / Qr:.1e}), "
               f"median {np.median(mags):.2f}, max {max(mags):.2f}")
    # NTT, one 60-bit limb: delta = INTT(2^j e_i)
    qn = primes[0]
    g = next(x for x in range(2, 1000) if pow(x, (qn - 1) // 2, qn) != 1)
    psi = pow(g, (qn - 1) // (2 * N), qn)
    assert pow(psi, N, qn) == qn - 1
    ninv = pow(N, -1, qn)
    stats = []
    for i in (0, 5, 17):
        for j in (0, 10, 30, 59, 63):
            # inverse negacyclic NTT of a unit vector at evaluation point psi^(2i+1)
            c = [(pow(2, j, qn) * ninv * pow(psi, -((2 * i + 1) * l) % (2 * N), qn)) % qn for l in range(N)]
            c = [x - qn if x > qn // 2 else x for x in c]
            stats.append(np.sqrt(np.mean(np.square(np.array(c, dtype=float)))) / qn)
    report("T6 NTT: every coefficient changes, rms ~ q/sqrt(12), any i and j",
           all(0.2 < x < 0.4 for x in stats),
           f"rms(delta)/q over i in (0,5,17), j in (0,10,30,59,63): {min(stats):.3f}..{max(stats):.3f} "
           f"(1/sqrt 12 = {1/math.sqrt(12):.3f})")
    return qn


# ================================================================ T7 checksums
def t7(qn):
    g = next(x for x in range(2, 1000) if pow(x, (qn - 1) // 2, qn) != 1)
    psi = pow(g, (qn - 1) // (2 * N), qn)
    ev = lambda p, x: sum(c * pow(x, k, qn) for k, c in enumerate(p)) % qn
    a = [random.randrange(qn) for _ in range(N)]
    b = [random.randrange(qn) for _ in range(N)]
    ab = mul(a, b, qn)
    hom = ev(ab, psi) == ev(a, psi) * ev(b, psi) % qn
    csum = sum(ab) % qn == (sum(a) * sum(b)) % qn
    resc = ev([x // (1 << 20) for x in a], psi) == ev(a, psi) * pow(1 << 20, -1, qn) % qn
    aut = [0] * N
    for k, c in enumerate(a):
        e = (5 * k) % (2 * N)
        if e < N:
            aut[e] = (aut[e] + c) % qn
        else:
            aut[e - N] = (aut[e - N] - c) % qn
    perm = ev(aut, psi) == ev(a, pow(psi, 5, qn))
    report("T7 evaluation at a root of X^N+1 is a ring homomorphism", hom and perm and not csum and not resc,
           f"eval(ab) = eval(a) eval(b): {hom}; coefficient sum multiplicative: {csum}; "
           f"survives a floor division: {resc}; automorphism moves psi -> psi^5: {perm}")



# ================================================================ T8 fresh noise, gap leak
def t8():
    """HEAAN encryptMsg: public-key encryption mod qQ, then >> logQ. The phase noise of a
    fresh ciphertext is the rounding of that division, not the Gaussian sigma. Predicts
    the onset of the gap leak through the noise of the other operand (one ct x ct mul)."""
    logq = logQ = 150
    n = 8
    qf, QQ, qQ = 1 << logq, 1 << (2 * logQ), 1 << (logq + logQ)
    kax = [random.randrange(QQ) for _ in range(N)]
    kbx = sub([round(random.gauss(0, 3.2)) % QQ for _ in range(N)], mul(kax, [x % QQ for x in s], QQ), QQ)
    rms = []
    for _ in range(20):
        z = [random.uniform(-1, 1) for _ in range(n)]
        m = encode(z, n, (1 << LOGD) * (1 << logQ))
        v = [random.choice([0, 0, 1, -1]) for _ in range(N)]
        ax = add(mul([x % qQ for x in v], [x % qQ for x in kax], qQ), [round(random.gauss(0, 3.2)) % qQ for _ in range(N)], qQ)
        bx = add(add(mul([x % qQ for x in v], [x % qQ for x in kbx], qQ), [round(random.gauss(0, 3.2)) % qQ for _ in range(N)], qQ), [x % qQ for x in m], qQ)
        ax, bx = shr(ax, logQ), shr(bx, logQ)
        phi = centered(add(bx, mul(ax, [x % qf for x in s], qf), qf), qf)
        noise = np.array([p_ - round(mm / (1 << logQ)) for p_, mm in zip(phi, m)], dtype=float)
        rms.append(np.sqrt(np.mean(noise[::N // (2 * n)] ** 2)))
    sig = float(np.mean(rms))
    b = 2 * LOGD + math.log2(1e-2 * math.sqrt(1 / 5) / (sig * math.sqrt(n)))
    report("T8 gap leak through the operand noise", 1.0 < sig < 2.5 and abs(b - 50) < 1.5,
           f"fresh noise rms per aligned coefficient {sig:.2f} (Gaussian sigma = 3.2); "
           f"predicted onset {b:.2f} (measured 50, aligned 24)")


if __name__ == "__main__":
    t1(); t2(); t3(); t4(); t5(); qn = t6(); t7(qn); t8()
