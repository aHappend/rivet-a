"""Byte-oriented FIPS 197 / SP 800-38D oracle, independent of DUT sources."""


def mul(a, b):
    z = 0
    while b:
        if b & 1:
            z ^= a
        a = ((a << 1) ^ (0x11B if a & 128 else 0)) & 255
        b >>= 1
    return z


def power(a, n):
    y = 1
    while n:
        if n & 1:
            y = mul(y, a)
        a = mul(a, a)
        n >>= 1
    return y


def substitute(a):
    x = power(a, 254) if a else 0
    return x ^ ((x << 1 | x >> 7) & 255) ^ ((x << 2 | x >> 6) & 255) ^ (
        (x << 3 | x >> 5) & 255
    ) ^ ((x << 4 | x >> 4) & 255) ^ 0x63


SBOX = bytes(substitute(i) for i in range(256))
INVERSE = bytes(SBOX.index(i) for i in range(256))


def aes(key, block, decrypt=False):
    assert len(key) in (16, 32) and len(block) == 16
    nk, nr = len(key) // 4, len(key) // 4 + 6
    words = [list(key[i:i + 4]) for i in range(0, len(key), 4)]
    rcon = 1
    for i in range(nk, 4 * (nr + 1)):
        t = words[-1][:]
        if i % nk == 0:
            t = [SBOX[x] for x in t[1:] + t[:1]]
            t[0] ^= rcon
            rcon = mul(rcon, 2)
        elif nk == 8 and i % nk == 4:
            t = [SBOX[x] for x in t]
        words.append([a ^ b for a, b in zip(words[i - nk], t)])
    keys = [sum(words[i:i + 4], []) for i in range(0, len(words), 4)]

    def shift(s, inverse=False):
        return [s[4 * ((c + (-r if inverse else r)) % 4) + r]
                for c in range(4) for r in range(4)]

    def mix(s, inverse=False):
        coefficients = (14, 11, 13, 9) if inverse else (2, 3, 1, 1)
        return [mul(s[4 * c], coefficients[-r % 4]) ^
                mul(s[4 * c + 1], coefficients[(1 - r) % 4]) ^
                mul(s[4 * c + 2], coefficients[(2 - r) % 4]) ^
                mul(s[4 * c + 3], coefficients[(3 - r) % 4])
                for c in range(4) for r in range(4)]

    def add(s, k):
        return [a ^ b for a, b in zip(s, k)]

    s = add(list(block), keys[nr if decrypt else 0])
    if decrypt:
        for r in range(nr - 1, -1, -1):
            s = add([INVERSE[x] for x in shift(s, True)], keys[r])
            if r:
                s = mix(s, True)
    else:
        for r in range(1, nr + 1):
            s = shift([SBOX[x] for x in s])
            if r != nr:
                s = mix(s)
            s = add(s, keys[r])
    return bytes(s)


def ctr(key, iv, data, first=1):
    result = bytearray()
    for offset in range(0, len(data), 16):
        counter = first + offset // 16
        assert counter <= 0xFFFFFFFF
        stream = aes(key, iv + counter.to_bytes(4, "big"))
        result.extend(a ^ b for a, b in zip(data[offset:offset + 16], stream))
    return bytes(result)


def polynomial(x, y):
    z = 0
    for bit in range(127, -1, -1):
        if x >> bit & 1:
            z ^= y
        y = (y >> 1) ^ (0xE1000000000000000000000000000000 if y & 1 else 0)
    return z


def gcm(key, iv, aad, data, decrypt=False):
    output = ctr(key, iv, data, 2)
    ciphertext = data if decrypt else output
    message = aad + bytes(-len(aad) % 16) + ciphertext + bytes(-len(ciphertext) % 16)
    message += (8 * len(aad)).to_bytes(8, "big") + (8 * len(data)).to_bytes(8, "big")
    h = int.from_bytes(aes(key, bytes(16)), "big")
    acc = 0
    for i in range(0, len(message), 16):
        acc = polynomial(acc ^ int.from_bytes(message[i:i + 16], "big"), h)
    mask = int.from_bytes(aes(key, iv + b"\0\0\0\1"), "big")
    return output, (acc ^ mask).to_bytes(16, "big")


def known_answers():
    # FIPS 197 Appendix C; SP 800-38D / NIST GCM example vectors.
    plain = bytes.fromhex("00112233445566778899aabbccddeeff")
    for size, expected in (
        (16, "69c4e0d86a7b0430d8cdb78070b4c55a"),
        (32, "8ea2b7ca516745bfeafc49904b496089")):
        key = bytes(range(size))
        encrypted = bytes.fromhex(expected)
        assert aes(key, plain) == encrypted
        assert aes(key, encrypted, True) == plain
    vectors = [
        (bytes(16), bytes(12), b"", b"", "", "58e2fccefa7e3061367f1d57a4e7455a"),
        (bytes(16), bytes(12), b"", bytes(16),
         "0388dace60b6a392f328c2b971b2fe78", "ab6e47d42cec13bdf53a67b21257bddf"),
        (bytes(32), bytes(12), b"", b"", "", "530f8afbc74536b9a963b4f1c4cb738b"),
        (bytes(32), bytes(12), b"", bytes(16),
         "cea7403d4d606b6e074ec5d3baf39d18", "d0d1c8a799996bf0265b98b5d48ab919"),
        (bytes.fromhex("feffe9928665731c6d6a8f9467308308"),
         bytes.fromhex("cafebabefacedbaddecaf888"),
         bytes.fromhex("feedfacedeadbeeffeedfacedeadbeefabaddad2"),
         bytes.fromhex("d9313225f88406e5a55909c5aff5269a"
                       "86a7a9531534f7da2e4c303d8a318a72"
                       "1c3c0c95956809532fcf0e2449a6b525"
                       "b16aedf5aa0de657ba637b39"),
         "42831ec2217774244b7221b784d0d49ce3aa212f2c02a4e035c17e2329aca12e"
         "21d514b25466931c7d8f6a5aac84aa051ba30b396a0aac973d58e091",
         "5bc94fbc3221a5db94fae95ae7121a47"),
    ]
    for key, iv, aad, data, ciphertext, tag in vectors:
        c, t = gcm(key, iv, aad, data)
        assert c.hex() == ciphertext and t.hex() == tag
        assert gcm(key, iv, aad, c, True) == (data, t)
        assert t != bytes([t[0] ^ 1]) + t[1:]
    return {"aes_fips197": 4, "gcm_nist": len(vectors) * 2}
