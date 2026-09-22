#include "heaan_inject.h"
#include "FaultHook.h"

#include <NTL/ZZ.h>
#include <algorithm>
#include <stdexcept>

namespace {

Injector*       g_inj       = nullptr;
// Flip pendiente de restaurar. El fork restaura con OTRO flip sobre el mismo poly
// (restoreIfStep == flipIfStep), asi que hay que distinguir "segundo flip = restore"
// de "segundo flip = segunda inyeccion".
bool            g_pending   = false;
const NTL::ZZX* g_last_poly = nullptr;   // direccion del poly flipeado
NTL::ZZ         g_original;              // valor del coeficiente ANTES del flip
NTL::ZZ         g_flipped;               // valor del coeficiente DESPUES del flip
long            g_N         = 0;

void fi_flip(NTL::ZZX& poly, uint32_t coeff, uint32_t bit, uint32_t width, long ring_degree)
{
    if (!g_inj) throw std::logic_error("flip call outside of run_iteration");
    Injector& inj = *g_inj;
    const long N = ring_degree > 0 ? ring_degree : g_N;

    if (inj.probing()) {
        long maxbits = 0;
        for (long i = 0; i < poly.rep.length(); ++i)
            maxbits = std::max(maxbits, NTL::NumBits(poly.rep[i]));
        inj.record_probe(1, uint32_t(maxbits));
        return;
    }
    const FaultSpec& f = inj.spec();
    if (coeff != f.coeff || bit != f.bit || width != f.amountBits)
        throw std::logic_error("the fork asked for a flip that does not match FaultSpec");
    if (long(coeff) >= N) throw std::out_of_range("coeff >= N");

    const long need = std::max<long>(long(coeff) + 1, N);   // igual que default_flip: estirar, NUNCA normalize
    if (poly.rep.length() < need) poly.SetLength(need);
    // Es el restore solo si hay un flip pendiente, es el MISMO poly y el coeficiente
    // tiene EXACTAMENTE el valor que dejo ese flip. Con "!= g_original" alcanzaba que
    // el puntero coincidiera, y &poly puede ser una direccion reusada por otro ZZX
    // (en heaan_nn.cpp los flips van a copias locales que mueren enseguida): ahi una
    // segunda inyeccion se contaba como restore y finish() no se enteraba.
    const bool is_restore = g_pending && (g_last_poly == &poly) &&
                            (NTL::coeff(poly, coeff) == g_flipped);
    const NTL::ZZX before = poly;
    for (uint32_t i = 0; i < width; ++i) NTL::SwitchBit(poly.rep[coeff], long(bit + i));

    if (is_restore) {
        if (poly.rep[coeff] != g_original) throw std::logic_error("the restore did not recover the original value");
        inj.record_restore();
        g_pending = false;
        g_last_poly = nullptr;
        return;
    }
    int flipped = 0;
    for (uint32_t i = 0; i < width; ++i)
        flipped += NTL::bit(before.rep[coeff], long(bit + i)) != NTL::bit(poly.rep[coeff], long(bit + i));
    int changed = 0;
    for (long i = 0; i < N; ++i)
        changed += NTL::coeff(before, i) != NTL::coeff(poly, i);
    g_original  = before.rep[coeff];
    g_flipped   = poly.rep[coeff];
    g_last_poly = &poly;
    g_pending   = true;
    inj.record_flip(flipped, changed);
}

} // namespace

InjectorScope::InjectorScope(Injector& inj, long ring_degree)
{
    if (g_inj) throw std::logic_error("Nested InjectorScope: already one active");
    heaanfi::set_flip(&fi_flip);
    g_inj       = &inj;
    g_N         = ring_degree;
    g_last_poly = nullptr;
    g_pending = false;
}

InjectorScope::~InjectorScope()
{
    g_inj       = nullptr;
    g_last_poly = nullptr;
}

void client_flip(Injector& inj, NTL::ZZX& poly)
{
    if (&inj != g_inj) throw std::logic_error("client_flip called with an Injector that is not the active scope");
    const FaultSpec& f = inj.spec();
    heaanfi::flip(poly, f.coeff, f.bit, f.amountBits, g_N);
}
