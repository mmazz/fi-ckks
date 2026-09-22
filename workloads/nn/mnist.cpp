#include "mnist.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <stdexcept>

std::string nn_data_dir()
{
    if (const char* env = std::getenv("FI_NN_DATA")) return env;
#ifdef FI_NN_DATA_DIR
    return FI_NN_DATA_DIR;
#else
    return "data";
#endif
}

std::vector<std::vector<double>> loadCSVMatrix(const std::string& path, size_t rows, size_t cols)
{
    std::ifstream file(path);
    if (!file.is_open()) throw std::runtime_error("Could not be opened " + path);

    std::vector<std::vector<double>> matrix;
    matrix.reserve(rows);
    std::string line, cell;
    while (matrix.size() < rows && std::getline(file, line)) {
        std::stringstream ss(line);
        std::vector<double> row;
        row.reserve(cols);
        while (row.size() < cols && std::getline(ss, cell, ',')) row.push_back(std::stod(cell));
        if (row.size() != cols)
            throw std::runtime_error(path + ": row " + std::to_string(matrix.size()) + " has " +
                                     std::to_string(row.size()) + " columns, they were expected " + std::to_string(cols));
        matrix.push_back(std::move(row));
    }
    if (matrix.size() != rows)
        throw std::runtime_error(path + ": " + std::to_string(matrix.size()) + " lines, they were expected " +
                                 std::to_string(rows));
    return matrix;
}

std::vector<double> loadCSVVector(const std::string& path, size_t size)
{
    std::ifstream file(path);
    if (!file.is_open()) throw std::runtime_error("Could not be opened " + path);

    std::vector<double> data;
    data.reserve(size);
    std::string line, cell;
    while (data.size() < size && std::getline(file, line)) {
        std::stringstream ss(line);
        while (data.size() < size && std::getline(ss, cell, ',')) data.push_back(std::stod(cell));
    }
    if (data.size() != size)
        throw std::runtime_error(path + ": " + std::to_string(data.size()) + " values, they were expected " +
                                 std::to_string(size));
    return data;
}

void loadMnistNormRowByIndex(const std::string& csvPath, size_t image_index,
                             size_t& outLabel, std::vector<double>& pixelsOut)
{
    std::ifstream file(csvPath);
    if (!file.is_open()) throw std::runtime_error("Could not be opened " + csvPath);

    std::string line;
    size_t current = 0;
    bool first = true;
    while (std::getline(file, line)) {
        // Si la primera linea no empieza con un numero es el header: no cuenta como imagen.
        if (first) {
            first = false;
            if (line.empty() || !std::isdigit(static_cast<unsigned char>(line[0]))) continue;
        }
        if (current++ != image_index) continue;

        std::stringstream ss(line);
        std::string cell;
        std::getline(ss, cell, ',');
        outLabel = std::stoul(cell);

        pixelsOut.clear();
        pixelsOut.reserve(NN_INPUT);
        constexpr double inv255 = 1.0 / 255.0;
        while (std::getline(ss, cell, ',')) {
            const int pixel = std::clamp(std::stoi(cell), 0, 255);
            pixelsOut.push_back(2.0 * (pixel * inv255) - 1.0);   // [-1, 1]
        }
        if (pixelsOut.size() != NN_INPUT)
            throw std::runtime_error(csvPath + ": the image " + std::to_string(image_index) + " has " +
                                     std::to_string(pixelsOut.size()) + " pixels");
        return;
    }
    throw std::runtime_error(csvPath + ": image " + std::to_string(image_index) +
                             " out of range (are " + std::to_string(current) + ")");
}

double cheby_tanh3(double x)
{
    return 0.98 * x - 0.23 * x * x * x;
}

std::vector<double> plain_forward(const std::vector<double>& x, const NNWeights& w)
{
    std::vector<double> layer1(w.W1.size());
    for (size_t j = 0; j < w.W1.size(); ++j) {
        double s = 0.0;
        for (size_t i = 0; i < x.size(); ++i) s += x[i] * w.W1[j][i];
        layer1[j] = cheby_tanh3(s + w.b1[j]);
    }

    std::vector<double> out(w.W2.size());
    for (size_t o = 0; o < w.W2.size(); ++o) {
        double acc = 0.0;
        for (size_t h = 0; h < layer1.size(); ++h) acc += layer1[h] * w.W2[o][h];
        out[o] = acc + w.b2[o];
    }
    return out;
}

NNModel load_nn_model(const std::string& data_dir, size_t image_index)
{
    NNModel m;
    m.weights.W1 = loadCSVMatrix(data_dir + "/weights/W1.csv", NN_HIDDEN, NN_INPUT);
    m.weights.b1 = loadCSVVector(data_dir + "/weights/b1.csv", NN_HIDDEN);
    m.weights.W2 = loadCSVMatrix(data_dir + "/weights/W2.csv", NN_OUTPUT, NN_HIDDEN);
    m.weights.b2 = loadCSVVector(data_dir + "/weights/b2.csv", NN_OUTPUT);

    loadMnistNormRowByIndex(data_dir + "/mnist_test.csv", image_index, m.label, m.image);
    m.plain_logits = plain_forward(m.image, m.weights);

    const size_t pred = size_t(std::max_element(m.plain_logits.begin(), m.plain_logits.end()) -
                               m.plain_logits.begin());
    if (pred != m.label)
        throw std::runtime_error("The plain network misclassifies the image " + std::to_string(image_index) +
                                 " (predicts " + std::to_string(pred) + ", label " + std::to_string(m.label) + ")");
    return m;
}
