#pragma once
// Mini framework de tests, sin dependencias. Cada test es una funcion registrada con TEST().
// El binario devuelve 0 si pasan todos; CTest se encarga del resto.
#include <functional>
#include <iostream>
#include <cmath>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace check {

struct Failure : std::runtime_error { using std::runtime_error::runtime_error; };

struct Test { std::string name; std::function<void()> fn; };

inline std::vector<Test>& registry()
{
    static std::vector<Test> tests;
    return tests;
}

struct Register {
    Register(const char* name, std::function<void()> fn) { registry().push_back({name, std::move(fn)}); }
};

// Para poder imprimir vectores en CHECK_EQ sin llenar la pantalla.
template <typename T>
std::ostream& operator<<(std::ostream& os, const std::vector<T>& v)
{
    os << "[" << v.size() << " values:";
    for (size_t i = 0; i < v.size() && i < 4; ++i) os << " " << v[i];
    return os << (v.size() > 4 ? " ...]" : "]");
}

[[noreturn]] inline void fail(const std::string& what, const char* file, int line)
{
    throw Failure(std::string(file) + ":" + std::to_string(line) + ": " + what);
}

template <typename A, typename B>
void eq(const A& a, const B& b, const char* expr, const char* file, int line)
{
    if (!(a == b)) {
        std::ostringstream os;
        os << expr << "  (" << a << " != " << b << ")";
        fail(os.str(), file, line);
    }
}

template <typename A, typename B>
void ne(const A& a, const B& b, const char* expr, const char* file, int line)
{
    if (a == b) fail(std::string(expr) + "  (both are equal)", file, line);
}

inline void near(double a, double b, double tol, const char* expr, const char* file, int line)
{
    if (!(std::abs(a - b) <= tol)) {
        std::ostringstream os;
        os << expr << "  (|" << a << " - " << b << "| > " << tol << ")";
        fail(os.str(), file, line);
    }
}

// Corre todos los tests registrados. Devuelve el codigo de salida del proceso.
inline int run_all()
{
    int failed = 0;
    for (const Test& t : registry()) {
        try {
            t.fn();
            std::cout << "  PASS  " << t.name << "\n" << std::flush;
        } catch (const std::exception& e) {
            ++failed;
            std::cout << "  FAIL  " << t.name << "\n        " << e.what() << "\n" << std::flush;
        }
    }
    std::cout << "== " << registry().size() - failed << " passed, " << failed << " failed ==\n";
    return failed == 0 ? 0 : 1;
}

} // namespace check

#define TEST(name)                                                    \
    static void name();                                               \
    static check::Register check_reg_##name(#name, name);             \
    static void name()

#define CHECK(cond)      do { if (!(cond)) check::fail("CHECK(" #cond ")", __FILE__, __LINE__); } while (0)
#define CHECK_EQ(a, b)   check::eq((a), (b), #a " == " #b, __FILE__, __LINE__)
#define CHECK_NE(a, b)   check::ne((a), (b), #a " != " #b, __FILE__, __LINE__)
#define CHECK_NEAR(a, b, tol) check::near((a), (b), (tol), #a " ~= " #b, __FILE__, __LINE__)
#define CHECK_THROWS(expr)                                            \
    do {                                                              \
        bool threw = false;                                           \
        try { expr; } catch (const std::exception&) { threw = true; } \
        if (!threw) check::fail("CHECK_THROWS(" #expr ")", __FILE__, __LINE__); \
    } while (0)
