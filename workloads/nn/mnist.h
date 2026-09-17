#pragma once
// Parte en claro del workload NN: carga de pesos e imagen, y forward de referencia.
// No depende de ninguna libreria HE; la usan heaan_nn.cpp y openfhe_nn.cpp.
#include <cstddef>
#include <string>
#include <vector>

// MLP 784 -> 64 -> 10, activacion 0.98*z - 0.23*z^3 (scripts/nn/trainingNeuralNetwork.py)
constexpr size_t NN_INPUT  = 784;
constexpr size_t NN_HIDDEN = 64;
constexpr size_t NN_OUTPUT = 10;

struct NNWeights {
    std::vector<std::vector<double>> W1;   // NN_HIDDEN x NN_INPUT
    std::vector<double>              b1;   // NN_HIDDEN
    std::vector<std::vector<double>> W2;   // NN_OUTPUT x NN_HIDDEN
    std::vector<double>              b2;   // NN_OUTPUT
};

// Todo lo que el workload necesita en claro. Se carga una vez en setup_campaign.
struct NNModel {
    NNWeights           weights;
    std::vector<double> image;          // NN_INPUT pixeles en [-1, 1]
    size_t              label = 0;
    std::vector<double> plain_logits;   // salida de referencia (NN_OUTPUT valores)
};

// Directorio con weights/{W1,b1,W2,b2}.csv y mnist_test.csv.
// Variable de entorno FI_NN_DATA si existe; si no, el que fijo CMake.
std::string nn_data_dir();

// Carga pesos + imagen `image_index` (0 = primera imagen del CSV, sin contar el header).
// Tira si falta algo o si la red en claro clasifica mal esa imagen.
NNModel load_nn_model(const std::string& data_dir, size_t image_index);

std::vector<std::vector<double>> loadCSVMatrix(const std::string& path, size_t rows, size_t cols);
std::vector<double> loadCSVVector(const std::string& path, size_t size);
// Pixeles normalizados a [-1, 1]: x = 2*(p/255) - 1
void loadMnistNormRowByIndex(const std::string& csvPath, size_t image_index,
                             size_t& outLabel, std::vector<double>& pixelsOut);

double cheby_tanh3(double x);   // 0.98*x - 0.23*x^3
std::vector<double> plain_forward(const std::vector<double>& x, const NNWeights& w);
