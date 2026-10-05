/*
 * Host harness: runs the FIRMWARE's InputEncoder over data fed on stdin so
 * it can be diffed against training/train_sltc.py::encode().
 *
 * Compiled for x86 by training/verify_encoder.py against a generated
 * sltc_weights.h, once per encoding. This is deliberately the real header
 * from tiva/, not a copy — a copy would be free to drift, which is the
 * exact failure this test exists to catch.
 *
 * stdin : one "x,y,z" line per sample, accelerometer values in g
 * stdout: one line per sample, INPUT comma-separated encoded channels
 */

#include <cstdio>
#include <cstdlib>

#include "sltcneuron.hpp"

int main()
{
    InputEncoder enc;
    char line[256];

    while (fgets(line, sizeof(line), stdin)) {
        float a[3];
        if (sscanf(line, "%f,%f,%f", &a[0], &a[1], &a[2]) != 3) continue;

        float out[sltc_weights::INPUT];
        enc.encode(a, out);

        for (int i = 0; i < sltc_weights::INPUT; ++i) {
            printf("%s%.9g", i ? "," : "", static_cast<double>(out[i]));
        }
        putchar('\n');
    }
    return 0;
}
