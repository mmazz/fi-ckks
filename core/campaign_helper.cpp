#include "campaign_helper.h"
#include "registry.h"

#include <getopt.h>
#include <cstdlib>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <map>
#include <set>


void CampaignArgs::print(std::ostream& os) const {
    os << "===== CampaignArgs =====\n";
    os << "library: " << library << '\n';
    os << "stage: " << stage << '\n';

    os << "bitsPerCoeff: " << bitsPerCoeff << '\n';
    os << "logN: " << logN << '\n';
    os << "logQ: " << logQ << '\n';
    os << "logDelta: " << logDelta << '\n';
    os << "logSlots: " << logSlots << '\n';
    os << "mult_depth: " << mult_depth << '\n';
    os << "logMin: " << logMin << '\n';
    os << "logMax: " << logMax << '\n';

    os << "seed: " << seed << '\n';
    os << "seed_input: " << seed_input << '\n';

    os << "withNTT: " << std::boolalpha << withNTT << '\n';
    os << "pipeline: " << pipeline << '\n';
    os << "op_step: " << op_step << '\n';
    os << "op_depth: " << op_depth << '\n';

    os << "isComplex: " << isComplex << '\n';
    os << "isExhaustive: " << isExhaustive << '\n';
    os << "verbose: " << verbose << '\n';

    os << "dnum: " << dnum << '\n';
    os << "amountBits: " << amountBits << '\n';
    os << "scaleTech: " << scaleTech << '\n';
    os << "results_dir: " << results_dir << '\n';
    os << "numSamples: " << numSamples << '\n';
    os << "saveVectors: " << saveVectors<< '\n';

    if (openfhe_attack_mode)
        os << "openfhe_attack_mode: " << static_cast<int>(*openfhe_attack_mode) << '\n';
    else
        os << "openfhe_attack_mode: <none>\n";

    if (openfhe_threshold_bits)
        os << "openfhe_threshold_bits: " << *openfhe_threshold_bits << '\n';
    else
        os << "openfhe_threshold_bits: <none>\n";

    os << "========================\n";
}



void print_usage(const char* program_name) {
    std::cout << "Usage: " << program_name << " [OPTIONS]\n\n"
              << "Options:\n"
              << "  --stage <name>          Stage to target: none, encode, encrypt_c0, encrypt_c1, decrypt_c0, decrypt_c1, decode, mul_inside, mul_outside, add_inside, add_outside, rot_inside, rot_outside (default: none)\n"
              << "  --bitsPerCoeff <value>  Max bits per coeff (default: 64)\n"
              << "  --logN <value>          log Ring dimension (default: 3 = 2^3 = 8)\n"
              << "  --logQ <value>          First mod bits (default: 60)\n"
              << "  --logDelta <value>      Scaling factor bits (default: 50)\n"
              << "  --logSlots <value>      log Slots used (default: 1)\n"
              << "  --mult_depth <value>    Multiplicative depth (only openfhe, default: 0)\n"
              << "  --withNTT <value>       Turn on or off NTT (only heaan, default: 0)\n"
              << "  --pipeline              TODO\n"
              << "  --op_step <value>       Index of the target operation within the selected stage (0-based, default: 0)\n"
              << "  --op_depth <value>      Depth within the selected operation where the bit flip is applied (0-based, default: 0)\n"
              << "  --isComplex <name>      Complex input, only for HEAAN (default: 0)\n"
              << "  --isExhaustive <name>   Type of bit flip campaign (default: exhaustive)\n"
              << "  --seed <value>          Random seed for scheme (default: 0)\n"
              << "  --seed_input <value>    Random seed for input (default: 0)\n"
              << "  --logMin <value>        logMin value (default: 0= sample from [-1,)\n"
              << "  --logMax <value>        logMax value (default: 0= sample up to ,1])\n"
              << "  --attackModeSKA <value> Type of error injection for SKA (only heaan, default: complete)\n"
              << "  --thresholdSKA <value>  Bits for threshold for SKA (only heaan, default: 5.0)\n"
              << "  --dnum <value>          Digit number (default: 3)\n"
              << "  --amountBits <value>    Amount of burst bits (default: 1)\n"
              << "  --numSamples <value>    Amount of injections (default: 50)\n"
              << "  --saveVectors <value>   Save the input output vectors (default: 0)\n"
              << "  --scaleTech <value>     Scaling technique (default: FIXEDMANUAL, others: FIXEDAUTO, FLEXIBLEAUTO or FLEXIBLEAUTOEXT)\n"
              << "  --results_dir <path>    Results directory (default: results)\n"
              << "  --verbose, -v           Verbose output\n"
              << "  --help, -h              Show this help\n\n"
              << "Examples:\n"
              << "  " << program_name << " --library openfhe --logN 16 --stage encrypt\n"
              << "  " << program_name << " --library heaan --logN 15 --logDelta 60 --seed 123\n"
              << "  " << program_name << " --stage mul --limbs 4 -v\n";
}

   // Nombres viejos -> nuevos, para que los configs viejos sigan andando.
   static std::string canonical_stage(const std::string& s) {
       static const std::map<std::string, std::string> alias = {
           {"add_inside", "add"},         {"mul_inside", "mul"},  {"mul_inside_asplos", "mul_asplos"},
           {"rescale_inside", "rescale"}, {"rot_inside", "rot"},  {"rot_inside_asplos", "rot_asplos"},
           {"boot_outside", "boot"},
       };
       static const std::set<std::string> valid = {
           "none", "encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode",
           "add", "pmul", "mul", "mul_asplos", "scalar", "rescale", "rot", "rot_asplos",
           "boot", "boot_coeff", "boot_eval", "boot_slot", "cheby_tanh3", "hidden_layer",
       };
       auto it = alias.find(s);
       const std::string st = (it != alias.end()) ? it->second : s;
       if (!valid.count(st)) throw std::invalid_argument("stage invalido: '" + s + "'");
       return st;
   }


CampaignArgs parse_arguments(int argc, char* argv[]) {
    CampaignArgs args;

    static struct option long_options[] = {
        {"stage",          required_argument, 0, 'S'},
        {"bitsPerCoeff",    required_argument, 0, 'c'},
        {"logN",           required_argument, 0, 'N'},
        {"logQ",           required_argument, 0, 'Q'},
        {"logDelta",       required_argument, 0, 'd'},
        {"logSlots",       required_argument, 0, 'g'},
        {"mult_depth",     required_argument, 0, 'm'},
        {"withNTT",        required_argument, 0, 'n'},
        {"pipeline", required_argument, 0, 'P'},
        {"op_step",        required_argument, 0, 'o'},
        {"op_depth",       required_argument, 0, 'O'},
        {"isComplex",      required_argument, 0, 'X'},
        {"isExhaustive",   required_argument, 0, 'T'},
        {"logMin",         required_argument, 0, 'x'},
        {"logMax",         required_argument, 0, 'y'},
        {"seed",           required_argument, 0, 's'},
        {"seed_input",     required_argument, 0, 'b'},
        // only Openfhe
        {"attackModeSKA",  required_argument, 0, 'a'},
        {"thresholdSKA",   required_argument, 0, 't'},
        {"dnum",           required_argument, 0, 'D'},
        {"amountBits",     required_argument, 0, 'J'},
        {"scaleTech",      required_argument, 0, 'C'},
        {"results_dir",    required_argument, 0, 'R'},
        {"numSamples",     required_argument, 0, 'K'},
        {"saveVectors",    required_argument, 0, 'V'},
        {"verbose",        no_argument,       0, 'v'},
        {"help",           no_argument,       0, 'h'},
        {0, 0, 0, 0}
    };

    int opt, option_index = 0;

    while ((opt = getopt_long(
        argc, argv,
        "S:c:N:Q:d:g:m:n:P:o:O:X:T:x:y:s:b:a:t:D:J:C:R:K:V:vh",
        long_options,
        &option_index)) != -1)
    {
        switch (opt) {

            case 'c': args.bitsPerCoeff = std::stoul(optarg); break;
            case 'N': args.logN = std::stoul(optarg); break;
            case 'Q': args.logQ = std::stoul(optarg); break;
            case 'd': args.logDelta = std::stoul(optarg); break;
            case 'm': args.mult_depth = std::stoul(optarg); break;
            case 's': args.seed = std::stoul(optarg); break;
            case 'b': args.seed_input = std::stoul(optarg); break;
            case 'x': args.logMin = std::stoul(optarg); break;
            case 'y': args.logMax = std::stoul(optarg); break;
            case 'D': args.dnum= std::stoul(optarg); break;
            case 'o': args.op_step = std::stoul(optarg); break;
            case 'O': args.op_depth = std::stoul(optarg); break;
            case 'J': args.amountBits = std::stoul(optarg); break;
            case 'K': args.numSamples = std::stoul(optarg); break;
            case 'V': args.saveVectors = std::stoul(optarg); break;

            case 'v':
                args.verbose = true;
                break;
            case 'g':
                args.logSlots = std::stoul(optarg);
                args.logSlots_provided = true;
                break;

            case 'n':  // --withNTT 0/1
                args.withNTT = std::stoul(optarg) != 0;
                break;
            case 'P': args.pipeline = optarg; break;
            case 'S':
                args.stage = canonical_stage(optarg); break;
               
            case 'X':
                args.isComplex= std::stoul(optarg);
                break;

            case 'T':
                args.isExhaustive = std::stoul(optarg) != 0;
                break;

            case 'a':
                args.openfhe_attack_mode =
                    parse_attack_mode(std::stoul(optarg));
                break;

            case 't':
                args.openfhe_threshold_bits =
                    std::stod(optarg);
                break;

            case 'C':
                args.scaleTech= optarg;
                break;

            case 'R':
                args.results_dir = optarg;
                break;

            case 'h':
                print_usage(argv[0]);
                std::exit(0);

            default:
                print_usage(argv[0]);
                std::exit(1);
        }
    }
   args.ops = parse_pipeline(args.pipeline);   // tira invalid_argument si esta mal
   args.pipeline = to_string(args.ops);        // canonico: es lo que va a la clave del registry
    if (!args.logSlots_provided) {
        if (args.logN == 0) {
            std::cerr << "Error: logN must be set if --logSlots is omitted\n";
            std::exit(1);
        }
        args.logSlots = args.logN - 1;
    }
    return args;
}


