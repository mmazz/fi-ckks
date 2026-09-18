// Determinismo de HEAAN a nivel ciphertext: misma seed -> mismos polinomios.
// No usa el framework de campanias: habla directo con la libreria.
#include "check.h"
#include "heaan_inject.h"

#include "HEAAN.h"
#include <NTL/ZZ.h>

#include <complex>
#include <memory>
#include <vector>

namespace {

constexpr long LOGN = 6, LOGQ = 120, LOGP = 30, LOGSLOTS = 4, HWT = 64;

// La seed de NTL fija la secret key y las claves de evaluacion.
SecretKey make_sk(uint64_t seed)
{
    NTL::SetSeed(NTL::ZZ(seed));
    return SecretKey(LOGN, HWT);
}

struct Env {
    Context   cc;
    SecretKey sk;
    Scheme    scheme;
    explicit Env(uint64_t seed) : cc(LOGN, LOGQ), sk(make_sk(seed)), scheme(sk, cc) {}
};

std::vector<std::complex<double>> message(long slots)
{
    std::vector<std::complex<double>> v(slots);
    for (long i = 0; i < slots; ++i) v[i] = {0.1 * double(i + 1), 0.0};
    return v;
}

Ciphertext encrypt(Env& env, uint64_t enc_seed)
{
    auto msg = message(1L << LOGSLOTS);
    Plaintext plain = env.scheme.encode(msg.data(), 1L << LOGSLOTS, LOGP, LOGQ);
    return env.scheme.encryptMsg(plain, NTL::ZZ(enc_seed));
}

} // namespace

// La misma seed de claves da la misma secret key.
TEST(same_seed_gives_same_key)
{
    Env a(7), b(7), c(8);
    CHECK(a.sk.sx == b.sk.sx);
    CHECK(!(a.sk.sx == c.sk.sx));
}

// La misma seed de cifrado da el mismo ciphertext, coeficiente por coeficiente.
TEST(same_seed_gives_same_ciphertext)
{
    Env env(7);
    Ciphertext c1 = encrypt(env, 42);
    Ciphertext c2 = encrypt(env, 42);
    CHECK(c1.ax == c2.ax);
    CHECK(c1.bx == c2.bx);
    CHECK_EQ(c1.logq, c2.logq);
    CHECK_EQ(c1.logp, c2.logp);
}

// Otra seed de cifrado da otro ciphertext (el ruido cambia).
TEST(other_seed_gives_other_ciphertext)
{
    Env env(7);
    Ciphertext c1 = encrypt(env, 42);
    Ciphertext c2 = encrypt(env, 43);
    CHECK(!(c1.ax == c2.ax));
}

// El ciphertext desencripta a lo que se cifro.
TEST(decrypt_recovers_message)
{
    Env env(7);
    Ciphertext c = encrypt(env, 42);
    Plaintext dec = env.scheme.decryptMsg(env.sk, c);
    std::unique_ptr<std::complex<double>[]> got(env.scheme.decode(dec));
    auto expected = message(1L << LOGSLOTS);
    for (long i = 0; i < (1L << LOGSLOTS); ++i)
        CHECK_NEAR(got[i].real(), expected[i].real(), 1e-6);
}

// El flip del cliente cambia un unico coeficiente, y volver a flipear lo restaura.
TEST(client_flip_changes_one_coeff_and_restores)
{
    Env env(7);
    Ciphertext c = encrypt(env, 42);
    const NTL::ZZX before = c.bx;

    FaultSpec f;
    f.stage = "encrypt_c0";
    f.coeff = 3;
    f.bit = 20;
    f.amountBits = 1;

    Injector inj = Injector::fault(f);
    {
        InjectorScope scope(inj, env.cc.N);
        client_flip(inj, c.bx);
    }
    inj.finish();

    int changed = 0;
    for (long i = 0; i < env.cc.N; ++i) changed += NTL::coeff(before, i) != NTL::coeff(c.bx, i);
    CHECK_EQ(changed, 1);
    CHECK_EQ(NTL::abs(NTL::coeff(c.bx, 3) - NTL::coeff(before, 3)), NTL::ZZ(1) << 20);

    Injector inj2 = Injector::fault(f);
    {
        InjectorScope scope(inj2, env.cc.N);
        client_flip(inj2, c.bx);
    }
    inj2.finish();
    CHECK(c.bx == before);
}

int main()
{
    std::cout << "== HEAAN a nivel ciphertext ==\n";
    return check::run_all();
}
