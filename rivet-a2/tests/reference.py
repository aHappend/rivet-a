"""Independent FIPS 197 / SP 800-38D models, using only integer arithmetic.

The S-box is derived by inversion and affine transformation, not an RTL table.
Byte arrays use the published column-major AES convention.
"""

from functools import lru_cache


def mul(a, b):
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        a = ((a << 1) ^ (0x11B if a & 128 else 0)) & 255
        b >>= 1
    return r


def power(a, n):
    r = 1
    while n:
        if n & 1:
            r = mul(r, a)
        a = mul(a, a)
        n >>= 1
    return r


def substitute(x):
    y = power(x, 254) if x else 0
    return y ^ 0x63 ^ (
        ((y << 1) | (y >> 7)) & 255
    ) ^ (((y << 2) | (y >> 6)) & 255) ^ (
        ((y << 3) | (y >> 5)) & 255
    ) ^ (((y << 4) | (y >> 4)) & 255)


SBOX = tuple(substitute(x) for x in range(256))
INV = tuple(SBOX.index(x) for x in range(256))


@lru_cache(maxsize=256)
def expand(key):
    assert len(key) in (16, 32)
    nk = len(key) // 4
    nr = nk + 6
    words = [list(key[i:i + 4]) for i in range(0, len(key), 4)]
    rc = 1
    for i in range(nk, 4 * (nr + 1)):
        t = words[-1][:]
        if i % nk == 0:
            t = [SBOX[x] for x in t[1:] + t[:1]]
            t[0] ^= rc
            rc = mul(rc, 2)
        elif nk == 8 and i % nk == 4:
            t = [SBOX[x] for x in t]
        words.append([x ^ y for x, y in zip(words[i - nk], t)])
    return tuple(bytes(sum(words[i:i + 4], []))
                 for i in range(0, len(words), 4))


def xor(a, b):
    assert len(a) == len(b)
    return bytes(x ^ y for x, y in zip(a, b))


def shift(s, inverse=False):
    return bytes(s[4 * ((c + (-r if inverse else r)) % 4) + r]
                 for c in range(4) for r in range(4))


def mix(s, inverse=False):
    first = (14, 11, 13, 9) if inverse else (2, 3, 1, 1)
    return bytes(
        mul(s[c * 4], first[(-r) % 4])
        ^ mul(s[c * 4 + 1], first[(1 - r) % 4])
        ^ mul(s[c * 4 + 2], first[(2 - r) % 4])
        ^ mul(s[c * 4 + 3], first[(3 - r) % 4])
        for c in range(4) for r in range(4)
    )


def aes(key, block, decrypt=False):
    assert len(block) == 16
    keys = expand(key)
    if decrypt:
        s = xor(block, keys[-1])
        for k in reversed(keys[1:-1]):
            s = mix(xor(bytes(INV[x] for x in shift(s, True)), k), True)
        return xor(bytes(INV[x] for x in shift(s, True)), keys[0])
    s = xor(block, keys[0])
    for k in keys[1:-1]:
        s = xor(mix(shift(bytes(SBOX[x] for x in s))), k)
    return xor(shift(bytes(SBOX[x] for x in s)), keys[-1])


def gf128(a, b):
    """Polynomial convolution and long division; unlike the RTL shift loop.

    SP 800-38D's leftmost bit represents coefficient x**0.
    """
    def reflect(x):
        return int(f"{x:0128b}"[::-1], 2)

    a, b = reflect(a), reflect(b)
    p = 0
    while b:
        if b & 1:
            p ^= a
        a <<= 1
        b >>= 1
    polynomial = (1 << 128) | (1 << 7) | (1 << 2) | (1 << 1) | 1
    while p.bit_length() > 128:
        p ^= polynomial << (p.bit_length() - 129)
    return reflect(p)


def blocks(data):
    return [data[i:i + 16] for i in range(0, len(data), 16)]


def gcm(key, iv, aad, plaintext):
    assert len(iv) == 12
    h = int.from_bytes(aes(key, bytes(16)), "big")
    ciphertext = b"".join(
        xor(b, aes(key, iv + (i + 2).to_bytes(4, "big"))[:len(b)])
        for i, b in enumerate(blocks(plaintext))
    )
    y = 0
    for b in blocks(aad) + blocks(ciphertext):
        y = gf128(y ^ int.from_bytes(b.ljust(16, b"\0"), "big"), h)
    lengths = (len(aad) * 8).to_bytes(8, "big") + (
        len(ciphertext) * 8).to_bytes(8, "big")
    y = gf128(y ^ int.from_bytes(lengths, "big"), h)
    tag = xor(aes(key, iv + b"\0\0\0\1"), y.to_bytes(16, "big"))
    return ciphertext, tag


def anchors():
    """Published anchors; return exact source locations for the evidence ledger."""
    hx = bytes.fromhex
    pt = hx("00112233445566778899aabbccddeeff")
    aes_rows = [
        ("000102030405060708090a0b0c0d0e0f",
         "69c4e0d86a7b0430d8cdb78070b4c55a"),
        ("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f",
         "8ea2b7ca516745bfeafc49904b496089"),
    ]
    ledger = []
    for k, c in aes_rows:
        key, ct = hx(k), hx(c)
        assert aes(key, pt) == ct, "FIPS 197 encryption anchor"
        assert aes(key, ct, True) == pt, "FIPS 197 decryption anchor"
        ledger.append(dict(kind="AES", key=k, plaintext=pt.hex(), ciphertext=c,
                           source="FIPS 197 (2001), Appendix C.1 and C.3",
                           url="https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.197.pdf"))
    rows = [
        (16, "", "", "", "58e2fccefa7e3061367f1d57a4e7455a"),
        (16, "", "00" * 16, "0388dace60b6a392f328c2b971b2fe78",
         "ab6e47d42cec13bdf53a67b21257bddf"),
        (32, "", "", "", "530f8afbc74536b9a963b4f1c4cb738b"),
        (32, "", "00" * 16, "cea7403d4d606b6e074ec5d3baf39d18",
         "d0d1c8a799996bf0265b98b5d48ab919"),
    ]
    for n, a, p, c, t in rows:
        ledger.append(dict(kind="GCM", key="00" * n, iv="00" * 12,
                           aad=a, plaintext=p, ciphertext=c, tag=t,
                           source=f"NIST GCM specification test case "
                                  f"{(1 if not p else 2) if n == 16 else (13 if not p else 14)}, "
                                  f"{'empty' if not p else 'one-block'}; "
                                  "McGrew/Viega GCM submission, Appendix B",
                           url="https://csrc.nist.gov/projects/block-cipher-techniques/bcm/modes-development"))
    plain = ("d9313225f88406e5a55909c5aff5269a"
             "86a7a9531534f7da2e4c303d8a318a72"
             "1c3c0c95956809532fcf0e2449a6b525"
             "b16aedf5aa0de657ba637b39")
    for n, c, t, case in [
        (16, "42831ec2217774244b7221b784d0d49c"
         "e3aa212f2c02a4e035c17e2329aca12e"
         "21d514b25466931c7d8f6a5aac84aa05"
         "1ba30b396a0aac973d58e091", "5bc94fbc3221a5db94fae95ae7121a47", 4),
        (32, "522dc1f099567d07f47f37a32a84427d"
         "643a8cdcbfe5c0c97598a2bd2555d1aa"
         "8cb08e48590dbb3da7b08b1056828838"
         "c5f61e6393ba7a0abcc9f662", "76fc6ece0f4e1768cddf8853bb2d551b", 16),
    ]:
        ledger.append(dict(kind="GCM", key="feffe9928665731c6d6a8f9467308308" * (n // 16),
                           iv="cafebabefacedbaddecaf888",
                           aad="feedfacedeadbeeffeedfacedeadbeefabaddad2",
                           plaintext=plain, ciphertext=c, tag=t,
                           source=f"McGrew/Viega GCM submission Appendix B, test case {case}",
                           url="https://csrc.nist.gov/CSRC/media/Projects/Block-Cipher-Techniques/documents/BCM/Proposed-Modes/gcm/gcm-spec.pdf"))
    for row in ledger:
        if row["kind"] == "GCM":
            c, t = gcm(hx(row["key"]), hx(row["iv"]), hx(row["aad"]),
                       hx(row["plaintext"]))
            assert c.hex() == row["ciphertext"], f"GCM anchor ciphertext: {row}"
            assert t.hex() == row["tag"], f"GCM anchor tag: {row}"
    return ledger
