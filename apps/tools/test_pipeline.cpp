#include "pipeline.h"
#include <iostream>
#include <stdexcept>

static int fails = 0;
static void expect_eq(const std::string& in, size_t n_ops, const std::string& canon) {
    try {
        auto ops = parse_pipeline(in);
        std::string out = to_string(ops);
        if (ops.size() != n_ops || out != canon) {
            std::cerr << "FAIL '" << in << "': " << ops.size() << " ops, canon='" << out << "'\n"; ++fails;
        }
    } catch (const std::exception& e) { std::cerr << "FAIL '" << in << "' tiro: " << e.what() << "\n"; ++fails; }
}
static void expect_throw(const std::string& in) {
    try { parse_pipeline(in); std::cerr << "FAIL '" << in << "' no tiro\n"; ++fails; }
    catch (const std::invalid_argument&) {}
}

int main() {
    expect_eq("",                               0, "");
    expect_eq("add x2; mul",                    3, "add x2; mul");
    expect_eq("mul; mul",                       2, "mul x2");
    expect_eq("  add ;; mul x3 ; ",             4, "add; mul x3");
    expect_eq("scalar 0.5 x2",                  2, "scalar 0.5 x2");
    expect_eq("scalar 0.1",                     1, "scalar 0.1");
    expect_eq("rot 4; rot 4; rot 2",            3, "rot 4 x2; rot 2");
    expect_eq("add; pmul; mul x2; rot 1; boot", 6, "add; pmul; mul x2; rot 1; boot");
    expect_throw("rot");
    expect_throw("rot 0");
    expect_throw("rot 1.5");
    expect_throw("foo");
    expect_throw("add 3");
    expect_throw("mul x0");
    expect_throw("scalar abc");
    expect_throw("scalar 1 2");
    std::cout << (fails ? "HAY FALLAS\n" : "OK\n");
    return fails ? 1 : 0;
}
