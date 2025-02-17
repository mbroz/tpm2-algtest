import os
import subprocess
import zipfile
import argparse
import sys
import glob
import csv
import datetime
import hashlib
import math

device = '/dev/tpm0'
image_tag = 'v1.0'

def zip(outdir):
    zipf = zipfile.ZipFile(outdir + '.zip', 'w', zipfile.ZIP_DEFLATED)
    for root, _, files in os.walk(outdir):
        for file in files:
            zipf.write(os.path.join(root, file))

def quicktest(args, detail_dir):
    if args.docker:
        run_command = [ 'docker', 'run', '-it', '--init', '--device=' + device,
                '--entrypoint=tpm2_getcap', 'simonstruk/tpm2-algtest:' + image_tag ]
    else:
        run_command = [ 'sudo', 'tpm2_getcap' ]
    run_command += [ '-T', 'device' ]

    print('Running quicktest...')
    with open(os.path.join(detail_dir, 'Quicktest_algorithms.txt'), 'w') as outfile:
        try:
            subprocess.run(run_command + ['-c', 'algorithms'], stdout=outfile).check_returncode()
        except:
            subprocess.run(run_command + ['algorithms'], stdout=outfile).check_returncode()

    with open(os.path.join(detail_dir, 'Quicktest_commands.txt'), 'w') as outfile:
        try:
            subprocess.run(run_command + ['-c', 'commands'], stdout=outfile).check_returncode()
        except:
            subprocess.run(run_command + ['commands'], stdout=outfile).check_returncode()

    with open(os.path.join(detail_dir, 'Quicktest_properties-fixed.txt'), 'w') as outfile:
        try:
            subprocess.run(run_command + ['-c', 'properties-fixed'], stdout=outfile).check_returncode()
        except:
            subprocess.run(run_command + ['properties-fixed'], stdout=outfile).check_returncode()

    with open(os.path.join(detail_dir, 'Quicktest_properties-variable.txt'), 'w') as outfile:
        try:
            subprocess.run(run_command + ['-c', 'properties-variable'], stdout=outfile).check_returncode()
        except:
            subprocess.run(run_command + ['properties-variable'], stdout=outfile).check_returncode()

    with open(os.path.join(detail_dir, 'Quicktest_ecc-curves.txt'), 'w') as outfile:
        try:
            subprocess.run(run_command + ['-c', 'ecc-curves'], stdout=outfile).check_returncode()
        except:
            subprocess.run(run_command + ['ecc-curves'], stdout=outfile).check_returncode()

    with open(os.path.join(detail_dir, 'Quicktest_handles-persistent.txt'), 'w') as outfile:
        try:
            subprocess.run(run_command + ['-c', 'handles-persistent'], stdout=outfile).check_returncode()
        except:
            subprocess.run(run_command + ['handles-persistent'], stdout=outfile).check_returncode()

def add_args(run_command, args):
    if args.num:
        run_command += [ '-n', str(args.num) ]
    if args.duration:
        run_command += [ '-d', str(args.duration) ]
    if args.keytype:
        run_command += [ '-t', args.keytype ]
    if args.keylen:
        run_command += [ '-l', str(args.keylen) ]
    if args.curveid:
        run_command += [ '-C', str(args.curveid) ]
    if args.command:
        run_command += [ '-c', args.command ]

def run_algtest(run_command, logfile):
    proc = subprocess.Popen(run_command, stdout=subprocess.PIPE, universal_newlines=True)
    for line in proc.stdout:
        sys.stdout.write(line + '\r')
        logfile.write(line)
    proc.wait()

def compute_rsa_privates(filename,sep=";"):
    def extended_euclidean(a, b):
        x0, x1, y0, y1 = 0, 1, 1, 0
        while a != 0:
            q, b, a = b // a, a, b % a
            y0, y1 = y1, y0 - q * y1
            x0, x1 = x1, x0 - q * x1
        return b, x0, y0

    def mod_exp(base, exp, n):
        res = 1
        base %= n
        while exp > 0:
            if exp % 2 == 1:
                res *= base
                res %= n
            exp //= 2
            base *= base
            base %= n
        return res

    def compute_row(row):
        try:
            n = int(row['n'], 16)
            e = int(row['e'], 16)
            p = int(row['p'], 16)
        except:
            return False
        q = n // p
        totient = (p - 1) * (q - 1)
        _, d, _ = extended_euclidean(e, totient)
        d %= totient

        message = 12345678901234567890
        assert mod_exp(mod_exp(message, e, n), d, n) == message, \
            f"Something went wrong (row {row['id']})"

        row['q'] = '%X' % q
        row['d'] = '%X' % d
        return True

    rows = []
    with open(filename) as infile:
        reader = csv.DictReader(infile, delimiter=sep)
        for row in reader:
            rows.append(row)

    failed = 0
    for row in rows:
        failed += 0 if compute_row(row) else 1

    if failed > 0:
        print(f"Computation of {failed} rows failed")

    with open(filename, 'w') as outfile:
        writer = csv.DictWriter(
                outfile, delimiter=sep, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

def keygen(args):
    detail_dir = os.path.join(args.outdir, 'detail')
    if args.docker:
        run_command = [ 'docker', 'run', '-it', '--init', '--device=' + device,
                '--volume=' + os.path.join(os.getcwd(), detail_dir) + ':/tpm2-algtest/build/out:z',
                'simonstruk/tpm2-algtest:' + image_tag ]
    else:
        run_command = [ 'sudo', 'build/tpm2_algtest', '--outdir=' + detail_dir ]
    run_command += ['-T', 'device', '-s', 'keygen' ]
    add_args(run_command, args)

    print('Running keygen test...')
    with open(os.path.join(detail_dir, 'keygen_log.txt'), 'w') as logfile:
        run_algtest(run_command, logfile)

    print('Computing RSA private keys...')
    for filename in glob.glob(os.path.join(detail_dir, 'Keygen:RSA_*.csv')):
        print(filename)
        compute_rsa_privates(filename)

def perf(args):
    detail_dir = os.path.join(args.outdir, 'detail')
    if args.docker:
        run_command = [ 'docker', 'run', '-it', '--init', '--device=' + device,
                '--volume=' + os.path.join(os.getcwd(), detail_dir) + ':/tpm2-algtest/build/out:z',
                'simonstruk/tpm2-algtest:' + image_tag ]
    else:
        run_command = [ 'sudo', 'build/tpm2_algtest', '--outdir=' + detail_dir ]
    run_command += ['-T', 'device', '-s', 'perf' ]
    add_args(run_command, args)

    print('Running perf test...')
    with open(os.path.join(detail_dir, 'perf_log.txt'), 'w') as logfile:
        run_algtest(run_command, logfile)

def compute_nonce(filename):
    CURVE_ORDER = {
        "P256": 0xffffffff00000000ffffffffffffffffbce6faada7179e84f3b9cac2fc632551,
        "P384": 0xffffffffffffffffffffffffffffffffffffffffffffffffc7634d81f4372ddf581a0db248b0a77aecec196accc52973,
        "BN256": 0xfffffffffffcf0cd46e5f25eee71a49e0cdc65fb1299921af62d536cd10b500d
    }

    def extract_ecdsa_nonce(n, r, s, x, e):
        # https://en.wikipedia.org/wiki/Elliptic_Curve_Digital_Signature_Algorithm
        return (pow(s, -1, n) * (e + (r * x) % n) % n) % n

    def extract_ecschnorr_nonce(n, r, s, x, e):
        # https://trustedcomputinggroup.org/wp-content/uploads/TPM2.0-Library-Spec-v1.16-Errata_v1.5_09212016.pdf
        return (s - (r * x) % n) % n

    def extract_sm2_nonce(n, r, s, x, e):
        # https://crypto.stackexchange.com/questions/9918/reasons-for-chinese-sm2-digital-signature-algorithm
        return (s + (s * x) % n + (r * x) % n) % n

    def extract_ecdaa_nonce(n, r, s, x, e):
        # https://trustedcomputinggroup.org/wp-content/uploads/TCG_TPM2_r1p59_Part1_Architecture_pub.pdf
        hasher = hashlib.sha256()
        hasher.update(int.to_bytes(r, byteorder="big", length=math.ceil(math.log2(n))))
        hasher.update(int.to_bytes(e, byteorder="big", length=math.ceil(math.log2(n))))
        h = int.from_bytes(hasher.digest(), byteorder="big")
        return (s - h * x) % n

    def compute_row(row):
        try:
            digest = int(row['digest'], 16)
            curve = { 0x3: "P256", 0x4: "P384", 0x10: "BN256" }[int(row['curve'], 16)]
            algorithm = { 0x18: "ECDSA", 0x1a: "ECDAA", 0x1b: "SM2", 0x1c: "ECSCHNORR" }[int(row['algorithm'], 16)]
            signature_r = int(row['signature_r'], 16)
            signature_s = int(row['signature_s'], 16)
            private_key = int(row['private_key'], 16)

            row['nonce'] = hex({
                "ECDSA": extract_ecdsa_nonce,
                "ECSCHNORR": extract_ecschnorr_nonce,
                "SM2": extract_sm2_nonce,
                "ECDAA": extract_ecdaa_nonce
            }[algorithm](CURVE_ORDER[curve], signature_r, signature_s, private_key, digest))[2:]

        except:
            return False
        return True

    rows = []
    with open(filename) as infile:
        reader = csv.DictReader(infile, delimiter=',')
        for row in reader:
            rows.append(row)

    failed = 0
    for row in rows:
        failed += 0 if compute_row(row) else 1

    if failed > 0:
        print(f"Computation of {failed} rows failed")

    with open(filename, 'w') as outfile:
        writer = csv.DictWriter(
                outfile, delimiter=',', fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

def cryptoops(args):
    detail_dir = os.path.join(args.outdir, 'detail')
    if args.docker:
        run_command = [ 'docker', 'run', '-it', '--init', '--device=' + device,
                '--volume=' + os.path.join(os.getcwd(), detail_dir) + ':/tpm2-algtest/build/out:z',
                'simonstruk/tpm2-algtest:' + image_tag ]
    else:
        run_command = [ 'sudo', 'build/tpm2_algtest', '--outdir=' + detail_dir ]
    run_command += ['-T', 'device', '-s', 'cryptoops' ]
    add_args(run_command, args)

    print('Running cryptoops test...')
    with open(os.path.join(detail_dir, 'cryptoops_log.txt'), 'w') as logfile:
        run_algtest(run_command, logfile)

    print('Computing ECC nonces...')
    for filename in glob.glob(os.path.join(detail_dir, 'Cryptoops_Sign:ECC_*.csv')):
        print(filename)
        compute_nonce(filename)

    print('Computing RSA privates...')
    for filename in glob.glob(os.path.join(detail_dir, 'Cryptoops_Sign:RSA_*.csv')):
        print(filename)
        compute_rsa_privates(filename, sep=",")


def rng(args):
    detail_dir = os.path.join(args.outdir, 'detail')
    if args.docker:
        run_command = [ 'docker', 'run', '-it', '--init', '--device=' + device,
                '--volume=' + os.path.join(os.getcwd(), detail_dir) + ':/tpm2-algtest/build/out:z',
                'simonstruk/tpm2-algtest:' + image_tag ]
    else:
        run_command = [ 'sudo', 'build/tpm2_algtest', '--outdir=' + detail_dir ]
    run_command += ['-T', 'device', '-s', 'rng' ]
    add_args(run_command, args)

    print('Running Rng test...')
    with open(os.path.join(detail_dir, 'rng_log.txt'), 'w') as logfile:
        run_algtest(run_command, logfile)


def get_tpm_id(detail_dir):
    def get_val(line):
        pos = line.find('0x')
        if pos == -1:
            return None
        val = line[line.find('0x') + 2:-1]
        return "0" * (8 - len(val)) + val

    manufacturer = ''
    vendor_str = ''
    fw = ''
    qt_properties = os.path.join(detail_dir, 'Quicktest_properties-fixed.txt')
    if os.path.isfile(qt_properties):
        with open(os.path.join(detail_dir, 'Quicktest_properties-fixed.txt'), 'r') as properties_file:
            lines = properties_file.readlines()
            fw1 = ''
            fw2 = ''
            for idx, line in enumerate(lines):
                val = get_val(lines[idx]) or get_val(lines[idx + 1])
                if line.startswith('TPM2_PT_MANUFACTURER'):
                    manufacturer = bytearray.fromhex(val).decode()
                elif line.startswith('TPM2_PT_FIRMWARE_VERSION_1'):
                    fw1 = val
                elif line.startswith('TPM2_PT_FIRMWARE_VERSION_2'):
                    fw2 = val
                elif line.startswith('TPM2_PT_VENDOR_STRING_'):
                    vendor_str += bytearray.fromhex(val).decode()
            fw = str(int(fw1[0:4], 16)) + '.' + str(int(fw1[4:8], 16)) + '.' + str(int(fw2[0:4], 16)) + '.' + str(int(fw2[4:8], 16))

    manufacturer = manufacturer.replace('\0', '')
    vendor_str = vendor_str.replace('\0', '')
    return manufacturer, vendor_str, fw

def write_header(file, manufacturer, vendor_str, fw):
    file.write('Tested and provided by;\n')
    file.write(f'Execution date/time; {datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")}\n')
    file.write(f'Manufacturer; {manufacturer}\n')
    file.write(f'Vendor string; {vendor_str}\n')
    file.write(f'Firmware version; {fw}\n')
    file.write(f'Image tag; {image_tag}\n\n')

def compute_stats(infile, *, rsa2048=False):
    ignore = 5 if rsa2048 else 0
    success, fail, sum_op, min_op, max_op, avg_op = 0, 0, 0, 10000000000, 0, 0
    error = None
    for line in infile:
        if line.startswith('duration'):
            continue
        if ignore > 0:
            ignore -= 1
            continue
        t, rc = line.split(',')[:2]
        rc = rc.replace(' ', '')
        rc = rc.replace('\n', '')
        if rc == '0000':
            success += 1
        else:
            error = rc
            fail += 1
            continue
        t = float(t)
        sum_op += t
        if t > max_op: max_op = t
        if t < min_op: min_op = t
    total = success + fail
    if success != 0:
        avg_op = (sum_op / success)
    else:
        min_op = 0

    return avg_op * 1000, min_op * 1000, max_op * 1000, total, success, fail, error # sec -> ms

def write_support_file(support_file, detail_dir):
        qt_properties = os.path.join(detail_dir, 'Quicktest_properties-fixed.txt')
        if os.path.isfile(qt_properties):
            support_file.write('\nQuicktest_properties-fixed\n')
            with open(os.path.join(detail_dir, 'Quicktest_properties-fixed.txt'), 'r') as infile:
                properties = ""
                for line in infile:
                    if line.startswith('  as UINT32:'):
                        continue
                    if line.startswith('  as string:'):
                        line = line[line.find('"'):]
                        properties = properties[:-1] + '\t' + line
                    else:
                        properties += line.replace(':', ';')
                support_file.write(properties)

        qt_algorithms = os.path.join(detail_dir, 'Quicktest_algorithms.txt')
        if os.path.isfile(qt_algorithms):
            support_file.write('\nQuicktest_algorithms\n')
            with open(qt_algorithms, 'r') as infile:
                for line in infile:
                    if line.startswith('  value:'):
                        line = line[line.find('0x'):]
                        support_file.write(line)

        qt_commands = os.path.join(detail_dir, 'Quicktest_commands.txt')
        if os.path.isfile(qt_commands):
            support_file.write('\nQuicktest_commands\n')
            with open(qt_commands, 'r') as infile:
                for line in infile:
                    if line.startswith('  commandIndex:'):
                        line = line[line.find('0x'):]
                        support_file.write(line)

        qt_ecc_curves = os.path.join(detail_dir, 'Quicktest_ecc-curves.txt')
        if os.path.isfile(qt_ecc_curves):
            support_file.write('\nQuicktest_ecc-curves\n')
            with open(os.path.join(detail_dir, 'Quicktest_ecc-curves.txt'), 'r') as infile:
                for line in infile:
                    line = line[line.find('(') + 1:line.find(')')]
                    support_file.write(line + '\n')

def write_perf_file(perf_file, detail_dir):
    perf_csvs = glob.glob(os.path.join(detail_dir, 'Perf_*.csv'))
    perf_csvs.sort()
    command = ''
    for filepath in perf_csvs:
        filename = os.path.basename(filepath)
        params_idx = filename.find(':')
        suffix_idx = filename.find('.csv')
        new_command = filename[5:suffix_idx if params_idx == -1 else params_idx]
        params = filename[params_idx+1:suffix_idx].split('_')
        if new_command != command:
            command = new_command
            perf_file.write('TPM2_' + command + '\n\n')

        if command == 'GetRandom':
            perf_file.write(f'Data length (bytes):;32\n')
        elif command in [ 'Sign', 'VerifySignature', 'RSA_Encrypt', 'RSA_Decrypt' ]:
            perf_file.write(f'Key parameters:;{params[0]} {params[1]};Scheme:;{params[2]}\n')
        elif command == 'EncryptDecrypt':
            perf_file.write(f'Algorithm:;{params[0]};Key length:;{params[1]};Mode:;{params[2]};Encrypt/decrypt?:;{params[3]};Data length (bytes):;256\n')
        elif command == 'HMAC':
            perf_file.write('Hash algorithm:;SHA-256;Data length (bytes):;256\n')
        elif command == 'Hash':
            perf_file.write(f'Hash algorithm:;{params[0]};Data length (bytes):;256\n')
        else:
            perf_file.write(f'Key parameters:;{" ".join(params)}\n')

        with open(filepath, 'r') as infile:
            avg_op, min_op, max_op, total, success, fail, error = compute_stats(infile)
            perf_file.write(f'operation stats (ms/op):;avg op:;{avg_op:.2f};min op:;{min_op:.2f};max op:;{max_op:.2f}\n')
            perf_file.write(f'operation info:;total iterations:;{total};successful:;{success};failed:;{fail};error:;{"None" if not error else error}\n\n')

def create_result_files(outdir):
    detail_dir = os.path.join(outdir, 'detail')
    manufacturer, vendor_str, fw = get_tpm_id(detail_dir)
    file_name = manufacturer + '_' + vendor_str + '_' + fw + '.csv'

    os.makedirs(os.path.join(outdir, 'results'), exist_ok=True)
    with open(os.path.join(outdir, 'results', file_name), 'w') as support_file:
        write_header(support_file, manufacturer, vendor_str, fw)
        write_support_file(support_file, detail_dir)

    os.makedirs(os.path.join(outdir, 'performance'), exist_ok=True)
    with open(os.path.join(outdir, 'performance', file_name), 'w') as perf_file:
        write_header(perf_file, manufacturer, vendor_str, fw)
        write_perf_file(perf_file, detail_dir)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('test', metavar='test', type=str)
    parser.add_argument('-n', '--num', type=int, required=False)
    parser.add_argument('-d', '--duration', type=int, required=False)
    parser.add_argument('-t', '--keytype', type=str, required=False)
    parser.add_argument('-l', '--keylen', type=int, required=False)
    parser.add_argument('-C', '--curveid', type=lambda x: int(x, 0), required=False)
    parser.add_argument('-c', '--command', type=str, required=False)
    parser.add_argument('-o', '--outdir', type=str, required=False, default='out')
    parser.add_argument('--docker', action='store_true')
    args = parser.parse_args()

    if not os.path.exists(device):
        print(f'Device {device} not found')
        return

    print('IMPORTANT: Please do not suspend or hibernate the computer while testing the TPM!')

    detail_dir = os.path.join(args.outdir, 'detail')
    if args.test == 'quicktest':
        os.makedirs(detail_dir, exist_ok=True)
        quicktest(args, detail_dir)
        zip(args.outdir)
    elif args.test == 'keygen':
        os.makedirs(detail_dir, exist_ok=True)
        keygen(args)
        zip(args.outdir)
    elif args.test == 'perf':
        os.makedirs(detail_dir, exist_ok=True)
        perf(args)
        zip(args.outdir)
    elif args.test == 'cryptoops':
        os.makedirs(detail_dir, exist_ok=True)
        cryptoops(args)
        zip(args.outdir)
    elif args.test == 'rng':
        os.makedirs(detail_dir, exist_ok=True)
        rng(args)
        zip(args.outdir)
    elif args.test == 'fulltest':
        os.makedirs(detail_dir, exist_ok=True)
        with open(os.path.join(detail_dir, 'image_tag.txt'), 'w') as f:
            f.write(image_tag)
        quicktest(args, detail_dir)
        keygen(args)
        cryptoops(args)
        rng(args)
        perf(args)
        create_result_files(args.outdir)
        zip(args.outdir)
        print('The tests are finished. Thank you! Please send us the generated file (' + args.outdir + '.zip).')
    elif args.test == 'format':
        if not os.path.exists(detail_dir):
            print('There is no output yet, need to run tests.')
            return
        create_result_files(args.outdir)
        print('Computing ECC nonces...')
        for filename in glob.glob(os.path.join(detail_dir, 'Cryptoops_Sign:ECC_*.csv')):
            print(filename)
            compute_nonce(filename)

        print('Computing RSA privates...')
        for filename in glob.glob(os.path.join(detail_dir, 'Cryptoops_Sign:RSA_*.csv')):
            print(filename)
            compute_rsa_privates(filename, sep=",")
        zip(args.outdir)
    else:
        print('invalid test type, needs to be one of: fulltest, quicktest, keygen, cryptoops, rng, perf, format')

if __name__ == '__main__':
    main()
