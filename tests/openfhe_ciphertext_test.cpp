// Determinismo de OpenFHE a nivel ciphertext: misma seed de la PRNG -> mismos polinomios RNS.
// No usa el framework de campanias: habla directo con la libreria.
#include "check.h"
#include "openfhe_inject.h"

#include "openfhe.h"

#include <vector>

using namespace lbcrypto;

namespace {

constexpr uint32_t LOGN = 6, LOGQ = 60, LOGP = 40, LOGSLOTS = 4, DEPTH = 1;

struct Env {
    CryptoContext<DCRTPoly> cc;
    KeyPair<DCRTPoly>       keys;

    explicit Env(uint64_t seed)
    {
        CCParams<CryptoContextCKKSRNS> params;
        params.SetMultiplicativeDepth(DEPTH);
        params.SetScalingModSize(LOGP);
        params.SetFirstModSize(LOGQ);
        params.SetBatchSize(1 << LOGSLOTS);
        params.SetRingDim(1 << LOGN);
        params.SetScalingTechnique(FIXEDMANUAL);
        params.SetSecurityLevel(HEStd_NotSet);

        PseudoRandomNumberGenerator::GetPRNG().SetSeed(seed);
        cc = GenCryptoContext(params);
        cc->Enable(PKE);
        cc->Enable(KEYSWITCH);
        cc->Enable(LEVELEDSHE);
        keys = cc->KeyGen();
    }
};

std::vector<double> message()
{
    std::vector<double> v(1 << LOGSLOTS);
    for (size_t i = 0; i < v.size(); ++i) v[i] = 0.1 * double(i + 1);
    return v;
}

Ciphertext<DCRTPoly> encrypt(Env& env, uint64_t enc_seed)
{
    PseudoRandomNumberGenerator::GetPRNG().SetSeed(enc_seed);
    return env.cc->Encrypt(env.keys.publicKey, env.cc->MakeCKKSPackedPlaintext(message()));
}

bool same_elements(const Ciphertext<DCRTPoly>& a, const Ciphertext<DCRTPoly>& b)
{
    return a->GetElements() == b->GetElements();
}

} // namespace

// La misma seed da la misma secret key.
TEST(same_seed_gives_same_key)
{
    Env a(7), b(7), c(8);
    CHECK(a.keys.secretKey->GetPrivateElement() == b.keys.secretKey->GetPrivateElement());
    CHECK(!(a.keys.secretKey->GetPrivateElement() == c.keys.secretKey->GetPrivateElement()));
}

// La misma seed de cifrado da el mismo ciphertext.
TEST(same_seed_gives_same_ciphertext)
{
    Env env(7);
    CHECK(same_elements(encrypt(env, 42), encrypt(env, 42)));
}

// Otra seed de cifrado da otro ciphertext (el ruido cambia).
TEST(other_seed_gives_other_ciphertext)
{
    Env env(7);
    CHECK(!same_elements(encrypt(env, 42), encrypt(env, 43)));
}

// El ciphertext desencripta a lo que se cifro.
TEST(decrypt_recovers_message)
{
    Env env(7);
    Ciphertext<DCRTPoly> c = encrypt(env, 42);
    Plaintext dec;
    env.cc->Decrypt(env.keys.secretKey, c, &dec);
    dec->SetLength(1 << LOGSLOTS);
    const std::vector<double> got = dec->GetRealPackedValue();
    const std::vector<double> expected = message();
    for (size_t i = 0; i < expected.size(); ++i) CHECK_NEAR(got[i], expected[i], 1e-6);
}

// inject() toca un unico coeficiente de un unico limb.
TEST(inject_changes_one_coeff)
{
    Env env(7);
    Ciphertext<DCRTPoly> c = encrypt(env, 42);
    const DCRTPoly before = c->GetElements()[0];

    FaultSpec f;
    f.stage = Stage::EncryptC0;
    f.limb = 0;
    f.coeff = 3;
    f.bit = 20;
    f.amountBits = 1;

    Injector inj = Injector::fault(f);
    inject(c->GetElements()[0], /*withNTT=*/false, inj);
    inj.finish();          // valida que se haya flipeado 1 bit en 1 coeficiente

    DCRTPoly after = c->GetElements()[0];
    after.SetFormat(Format::COEFFICIENT);
    DCRTPoly clean = before;
    clean.SetFormat(Format::COEFFICIENT);
    int changed = 0;
    for (size_t t = 0; t < clean.GetAllElements().size(); ++t)
        for (size_t i = 0; i < clean.GetAllElements()[t].GetLength(); ++i)
            changed += clean.GetAllElements()[t][i] != after.GetAllElements()[t][i];
    CHECK_EQ(changed, 1);
}

// El probe mide la cantidad de limbs y el ancho de los coeficientes.
TEST(probe_measures_limbs_and_bits)
{
    Env env(7);
    Ciphertext<DCRTPoly> c = encrypt(env, 42);
    Injector probe = Injector::probe(Stage::EncryptC0, 0, 0);
    inject(c->GetElements()[0], false, probe);
    probe.finish();
    CHECK_EQ(probe.probed_limbs(), uint32_t(DEPTH + 1));
    CHECK(probe.probed_coeff_bits() > 0);
    CHECK(probe.probed_coeff_bits() <= 64);
}

int main()
{
    std::cout << "== OpenFHE a nivel ciphertext ==\n";
    return check::run_all();
}
