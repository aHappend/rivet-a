"""Public transaction stimulus; expectations are computed before simulation."""
import random
import struct

from oracle import aes, ctr, gcm


def hexsv(data, width=None, little=False):
    return f"{width or len(data)*8}'h{int.from_bytes(data, 'little' if little else 'big'):x}"


def descriptor(mode=2, direction=0, ctx=0, slot=0, first=1, last=1,
               aad=b"", data=b"", iv=bytes(12), tag=bytes(16), cookie=37,
               aa=0x4000, src=0x6000, dst=0x8000, status=0xA000):
    control = mode | direction << 2 | ctx << 3 | slot << 5 | first << 7 | last << 8
    return struct.pack("<7I", control, aa, src, dst, status, len(aad), len(data)) + (
        iv + tag + bytes([cookie]) + bytes(7))


class Cases:
    def __init__(self, capacity, seed):
        self.capacity = capacity
        self.rng = random.Random(seed)
        self.lines = [f"rng=32'd{seed};"]
        self.keys = [bytes(range(16)), bytes(range(32)), bytes(range(16, 32)),
                     bytes(range(32, 64))]
        self.cookie = 0
        self.completions = 0
        self.tags = 0
        self.coverage = {}
        self.case_names = []

    def emit(self, line):
        self.lines.append(line)

    def data(self, count):
        return self.rng.randbytes(count)

    def mark(self, name):
        self.emit(f'finish_case; $display("CASE {name}");')
        self.case_names.append(name)

    def load(self, slot, lock=0, code=0, key=None):
        value = key if key is not None else self.keys[slot]
        self.emit(f"load_key({slot},{hexsv(value.ljust(32, bytes(1)))},"
                  f"{int(len(value)==32)},{lock},{code});")

    def initialize(self):
        self.emit("csr(0,0,0,32'h52415633,0); csr(8,0,0,0,0); csr(12,0,0,0,0);")
        self.emit("in_valid=1; cmd_valid=1; tick;"
                  "if(err_unloaded_key!==1 || in_ready!==0 || cmd_ready!==0)"
                  ' $fatal(1,"unloaded key semantics"); reset_device;')
        self.completion(36,code=2)
        self.submit(descriptor(cookie=36))
        self.mark("enhanced_invalid_key_no_backpressure")
        for slot in range(4):
            self.load(slot)
        self.emit("csr(8,0,0,15,0);")
        self.mark("reset_unloaded_four_slots")

    def completion(self, cookie, ctx=0, code=0, final=1, tag=bytes(16)):
        self.emit(f"expect_completion({cookie},{ctx},{code},{final},{hexsv(tag)});")
        self.completions += 1

    def output(self, data, direction=0, mode=2, tid=0, gate=None):
        if gate is None:
            gate = self.completions + self.tags
        for i in range(0, len(data), 16):
            beat = data[i:i + 16]
            self.emit(f"expect_output({hexsv(beat.ljust(16, bytes(1)))},"
                      f"{len(beat)},{direction},{int(mode==2)},{tid},{gate});")

    def beats(self, data, aad=0, bad_count=None, bad_section=None):
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            # Deliberately nonzero ignored lanes.
            value = chunk + b"\xdd" * (16 - len(chunk))
            count = bad_count if bad_count is not None else len(chunk)
            section = bad_section if bad_section is not None else aad
            self.emit(f"beat({hexsv(value)},{count},{section});")
            if bad_count is not None or bad_section is not None:
                break

    def submit(self, desc):
        self.emit(f"submit({hexsv(desc, little=True)});")

    def direct(self, mode, direction, slot, data, aad=b"", iv=None, bad_tag=False,
               legacy=False, ctx=0, name=None):
        iv = self.data(12) if iv is None else iv
        key = self.keys[slot]
        if mode == 0:
            expected = b"".join(aes(key, data[i:i + 16], bool(direction))
                                for i in range(0, len(data), 16))
            tag = bytes(16)
        elif mode == 1:
            expected, tag = ctr(key, iv, data), bytes(16)
        else:
            expected, tag = gcm(key, iv, aad, data, bool(direction))
        supplied = bytes([tag[0] ^ int(bad_tag)]) + tag[1:]
        if legacy:
            self.tags += 1
            self.emit(f"expect_tag({hexsv(tag)},{int(direction and not bad_tag)},"
                      f"{int(bad_tag)},0);")
        else:
            self.cookie = (self.cookie + 1) & 255
            self.completion(self.cookie, ctx, 7 if bad_tag else 0, 1,
                            bytes(16) if bad_tag else tag)
        if not bad_tag:
            self.output(expected, direction, mode)
        if legacy:
            self.emit(f"command({hexsv(iv)},{len(aad)},{len(data)},"
                      f"{direction},{hexsv(supplied)});")
        else:
            self.submit(descriptor(mode=mode, direction=direction, ctx=ctx,
                                   slot=slot, aad=aad, data=data, iv=iv, tag=supplied,
                                   cookie=self.cookie))
        self.beats(aad, 1)
        self.beats(data)
        self.mark(name or f"direct_{mode}_{direction}_{len(key)*8}_{len(data)}")

    def basic(self):
        self.initialize()
        saved=self.keys[0]
        for length in (16,32):
            self.keys[0]=bytes(length)
            self.load(0)
            for size in (0,16):
                for direction in (0,1):
                    data=bytes(size)
                    if direction:
                        data,_=gcm(self.keys[0],bytes(12),b"",data)
                    self.direct(2,direction,0,data,iv=bytes(12),
                                name=f"published_gcm_{length*8}_{size}_{direction}")
            self.keys[0]=saved
        self.load(0)
        for slot in (0, 1):
            for direction in (0, 1):
                raw_data = self.data(16)
                tid = self.rng.randrange(1, 256)
                # Legacy always uses slot zero; reload to exercise both lengths.
                self.load(0, key=self.keys[slot])
                self.output(aes(self.keys[slot], raw_data, bool(direction)),
                            direction, 0, tid, 0)
                self.emit(f"raw({hexsv(raw_data)},{direction},{tid});")
                self.mark(f"legacy_ecb_{slot}_{direction}")
                self.load(0)
                for mode in (0, 1, 2):
                    size = 16 if mode == 0 else min(17, self.capacity * 16)
                    self.direct(mode, direction, slot, self.data(size),
                                self.data(19) if mode == 2 else b"")
                saved_key=self.keys[0]
                self.keys[0]=self.keys[slot]
                self.load(0)
                self.direct(2, direction, 0, self.data(min(15, 16*self.capacity)),
                            self.data(3), legacy=True,
                            name=f"legacy_gcm_{slot}_{direction}")
                self.keys[0]=saved_key
                self.load(0)
                if direction:
                    self.direct(2, 1, slot, self.data(1), self.data(17), bad_tag=True,
                                name=f"bad_tag_{slot}")
        self.direct(2, 1, 0, self.data(1), legacy=True, bad_tag=True,
                    name="legacy_bad_tag")
        # Hold each dependent retirement for a guaranteed, compared stall window.
        data=self.data(1);iv=self.data(12)
        out,tag=gcm(self.keys[0],iv,b"",data)
        self.completion(249,tag=tag)
        self.output(out)
        self.emit("random_ready=0;completion_ready=0;out_ready=0;tag_ready=0;")
        self.submit(descriptor(data=data,iv=iv,cookie=249))
        self.beats(data)
        self.emit("while(!completion_valid) tick;repeat(5) tick;"
                  "if(out_valid!==0 || busy!==1)"
                  ' $fatal(1,"completion reservation released ownership");'
                  "csr(4,0,0,1,0);csr(20,1,0,0,1);completion_ready=1;"
                  "while(completions_seen<completions_added) tick;"
                  "while(!out_valid) tick;repeat(5) tick;"
                  "csr(4,0,0,1,0);csr(20,1,0,0,1);random_ready=1;")
        self.mark("direct_completion_before_output_stalls")
        self.tags+=1
        self.emit(f"expect_tag({hexsv(tag)},0,0,0);")
        self.output(out)
        self.emit("random_ready=0;tag_ready=0;out_ready=0;completion_ready=0;")
        self.emit(f"command({hexsv(iv)},0,1,0,128'h0);")
        self.beats(data)
        self.emit("while(!tag_valid) tick;repeat(5) tick;"
                  "if(out_valid!==0) $fatal(1,\"legacy payload before tag\");"
                  "tag_ready=1;while(tags_seen<tags_added) tick;"
                  "while(!out_valid) tick;repeat(5) tick;random_ready=1;")
        self.mark("legacy_tag_before_output_stalls")

    def boundaries(self, maximum=False):
        sizes = [0, 1, 15, 16, 16*self.capacity]
        if self.capacity > 1:
            sizes += [17]
        for slot in (0, 1):
            for size in sorted(set(sizes)):
                self.direct(2, 0, slot, self.data(size), self.data(17),
                            ctx=slot+2,
                            name=f"length_gcm_{slot}_{size}")
                self.direct(1, 1, slot, self.data(size),
                            ctx=slot+2,
                            name=f"length_ctr_{slot}_{size}")
            self.direct(0, 0, slot, b"", name=f"empty_ecb_{slot}")
        # Reject capacity before asking for or releasing any data.
        self.completion(215, code=5)
        self.submit(descriptor(data=bytes(16*self.capacity+1), cookie=215))
        self.mark("capacity_plus_one")

    def tag_bits(self):
        for bit in range(128):
            slot=bit&1;iv=self.data(12)
            ciphertext,tag=gcm(self.keys[slot],iv,b"",self.data(1))
            wrong=(int.from_bytes(tag,"big")^(1<<bit)).to_bytes(16,"big")
            self.completion(63,code=7)
            self.submit(descriptor(direction=1,slot=slot,data=ciphertext,iv=iv,
                                   tag=wrong,cookie=63))
            self.beats(ciphertext)
            self.mark(f"authentication_rejects_tag_bit_{bit}")

    def interleave(self, dma=False):
        sessions = []
        for ctx in range(4):
            iv = self.data(12)
            data = self.data(min(17,16*self.capacity))
            aad = self.data(19)
            direction = ctx & 1
            out, tag = gcm(self.keys[ctx], iv, aad, data, bool(direction))
            sessions.append((iv,aad,data,out,tag,direction))
        # Empty first fragment; then AAD split inside a block; data split at byte 1.
        for phase in range(5):
            if phase==1:
                self.emit("csr(12,0,0,15,0);csr(4,0,0,0,0);")
                data=self.data(16)
                self.output(aes(self.keys[0],data,True),direction=1,mode=0,tid=201,gate=0)
                self.emit(f"raw({hexsv(data)},1,201);")
                self.mark(f"raw_between_{'dma' if dma else 'direct'}_saved_contexts")
                self.emit("csr(12,0,0,15,0);")
            for ctx in self.rng.sample(list(range(4)),4):
                iv,aad,data,out,tag,direction=sessions[ctx]
                a = b"" if phase in (0,3,4) else aad[:1] if phase==1 else aad[1:]
                p = data[:1] if phase==3 else data[1:] if phase==4 else b""
                first,last = int(phase==0),int(phase==4)
                self.cookie=(self.cookie+1)&255
                self.completion(self.cookie,ctx,0,last,tag if last else bytes(16))
                desc=descriptor(direction=direction,ctx=ctx,slot=ctx,first=first,last=last,
                                aad=a,data=p,iv=iv,tag=tag,cookie=self.cookie,
                                aa=0x4000+ctx*0x100,src=0x6000+ctx*0x100,
                                dst=0x8000+ctx*0x100+(1 if phase==4 else 0),
                                status=0xA000+ctx*0x40)
                if last and not dma:
                    self.output(out,direction,2)
                if dma:
                    self.dma_job(desc,a,p,out[1:] if phase==4 else out[:1] if phase==3 else b"",
                                 tag if last else bytes(16), total=len(data) if last else
                                 1 if phase==3 else 0, final=last,
                                 retained=[(0x8000+ctx*0x100,out[:1])] if last else [])
                else:
                    self.submit(desc);self.beats(a,1);self.beats(p)
                self.mark(f"{'dma' if dma else 'direct'}_interleave_{phase}_{ctx}")
                if phase==0:
                    self.load(ctx, code=3)
                if phase==3:
                    # Rejections must leave cryptographic continuation state unchanged.
                    for mismatch in ("slot","direction","iv","aad_phase","mode","first"):
                        options=dict(direction=direction,ctx=ctx,slot=ctx,first=0,last=0,
                                     iv=iv,cookie=61)
                        options.update({
                            "slot":{"slot":(ctx+1)%4},
                            "direction":{"direction":1-direction},
                            "iv":{"iv":bytes(x^1 for x in iv)},
                            "aad_phase":{"aad":b"x"},
                            "mode":{"mode":1},
                            "first":{"first":1},
                        }[mismatch])
                        self.completion(61,ctx,4,0)
                        bad=descriptor(**options)
                        if dma:
                            self.dma_job(bad,b"",b"",b"",bytes(16),code=4,
                                         total=0 if mismatch=="first" else 1,final=0)
                        else:
                            self.submit(bad)
                        self.mark(f"{'dma' if dma else 'direct'}_preserve_{mismatch}_{ctx}")
                    # Same binding, but origin mismatch (DMA vs direct) is also invalid.
                    self.completion(62,ctx,4,0)
                    bad=descriptor(direction=direction,ctx=ctx,slot=ctx,first=0,last=0,
                                   iv=iv,cookie=62)
                    if dma:
                        self.submit(bad)
                    else:
                        self.dma_job(bad,b"",b"",b"",bytes(16),code=4,total=1,final=0)
                    self.mark(f"{'dma' if dma else 'direct'}_origin_preserved_{ctx}")
        self.emit("csr(12,0,0,0,0);")
        self.mark("contexts_released")

    def full_retention(self):
        sessions=[]
        for ctx in range(4):
            iv=self.data(12);aad=self.data(1);data=self.data(self.capacity*16)
            out,tag=gcm(self.keys[ctx],iv,aad,data,bool(ctx&1))
            sessions.append((iv,aad,data,out,tag))
        for phase in range(3):
            for ctx in range(4):
                iv,aad,data,out,tag=sessions[ctx]
                first,last=int(phase==0),int(phase==2)
                fragment=data[:1] if first else data[-1:] if last else data[1:-1]
                address=0xB000+ctx*0x1100
                destination=address if first else address+16 if last else address+32
                self.completion(100+ctx,ctx,0,last,tag if last else bytes(16))
                desc=descriptor(direction=ctx&1,ctx=ctx,slot=ctx,first=first,last=last,
                                aad=aad if first else b"",data=fragment,iv=iv,tag=tag,
                                dst=destination,status=0x11000+ctx*32)
                retained=[(address,out[:1]),(address+32,out[1:-1])] if last else []
                self.dma_job(desc,aad if first else b"",fragment,out[-1:] if last else b"",
                             tag if last else bytes(16),cookie=100+ctx,
                             total=len(data) if last else 1 if first else len(data)-1,
                             final=last,retained=retained)
                self.mark(f"four_bank_exact_capacity_{phase}_{ctx}")
        # A nonempty payload followed by an empty final fragment authenticates once.
        iv=self.data(12);data=self.data(1)
        out,tag=gcm(self.keys[0],iv,b"",data)
        self.completion(111,final=0)
        self.submit(descriptor(last=0,data=data,iv=iv,cookie=111));self.beats(data)
        self.mark("payload_before_empty_final")
        self.completion(112,tag=tag);self.output(out)
        self.submit(descriptor(first=0,iv=iv,tag=tag,cookie=112))
        self.mark("empty_final_uses_aggregate_lengths")

    def put(self, address, value, read=False):
        for i,byte in enumerate(value):
            self.emit(f"memory[{address+i}]=8'h{byte:02x};")
        if read and value:
            for aligned in range(address & ~15,(address+len(value)+15)&~15,16):
                self.emit(f"readable[{aligned}]=1;")

    def expect_write(self, address, value):
        for i,byte in enumerate(value):
            self.emit(f"write_value[{address+i}]=8'h{byte:02x};"
                      f"write_left[{address+i}]=write_left[{address+i}]+1;")

    def dma_job(self, desc, aad, data, output, tag, code=0, total=None, final=1,
                retained=(), addr=0x2000, cookie=None, priority=0, fault=None,
                enqueue=True, status=True, expect_payload=True):
        aa,src,dst,st = struct.unpack_from("<4I",desc,4)
        cookie = desc[56] if cookie is None else cookie
        self.put(addr,desc,True);self.put(aa,aad,True);self.put(src,data,True)
        self.emit(f"fetch_expected[fetch_added]={addr};fetch_added=fetch_added+1;")
        if final and expect_payload and code==0:
            for address,value in retained:
                self.expect_write(address,value)
            self.expect_write(dst,output)
        if status:
            status_bytes=struct.pack("<II",code,len(data) if total is None else total)
            status_bytes+=bytes([cookie,(desc[0]>>3)&3,final])+bytes(5)+tag
            self.expect_write(st,status_bytes)
        if fault is not None:
            address,write,skip=fault
            self.emit(f"fault_address={address};fault_write={write};fault_skip={skip};")
        if enqueue:
            self.emit(f"enqueue({addr},{priority},{cookie});")

    def dma_modes(self):
        for mode in (0,1,2):
            for slot in (0,1):
                for direction in (0,1):
                    offset=(mode*4+slot*2+direction)%16
                    aad=self.data(17) if mode==2 else b""
                    data=self.data(16 if mode==0 else min(17,self.capacity*16))
                    iv=self.data(12)
                    if mode==0:
                        out=aes(self.keys[slot],data,bool(direction));tag=bytes(16)
                    elif mode==1:
                        out=ctr(self.keys[slot],iv,data);tag=bytes(16)
                    else:
                        out,tag=gcm(self.keys[slot],iv,aad,data,bool(direction))
                    cookie=140+mode*4+slot*2+direction
                    self.completion(cookie,slot,tag=tag)
                    desc=descriptor(mode,direction,slot,slot,aad=aad,data=data,iv=iv,tag=tag,
                                    cookie=1,aa=0x4000+offset,src=0x6000+offset,
                                    dst=0x8000+offset)
                    self.dma_job(desc,aad,data,out,tag,cookie=cookie)
                    self.mark(f"dma_mode_{mode}_{slot}_{direction}_offset_{offset}")
        for offset in range(16):
            data=self.data(1);iv=self.data(12)
            out=ctr(self.keys[0],iv,data)
            self.completion(180+offset)
            desc=descriptor(mode=1,data=data,iv=iv,src=0x6000+offset,
                            dst=0x6000+offset)
            self.dma_job(desc,b"",data,out,bytes(16),cookie=180+offset)
            self.mark(f"dma_inplace_offset_{offset}")
        # Authenticate before any payload write.
        data=self.data(min(17,16*self.capacity));aad=self.data(1);iv=self.data(12)
        out,tag=gcm(self.keys[1],iv,aad,data,True)
        self.completion(220,code=7)
        desc=descriptor(direction=1,slot=1,data=data,aad=aad,iv=iv)
        self.dma_job(desc,aad,data,b"",bytes(16),code=7,cookie=220)
        self.mark("dma_auth_fail_no_write")

    def errors(self):
        # CSR access permissions, reserved fields, alignment, and W1C.
        for address,write,value in ((0,1,0),(4,1,0),(8,1,0),(12,1,0),
                                    (20,0,0),(20,1,4),(16,1,1),(1,0,0),(24,0,0)):
            self.emit(f"csr({address},{write},{value},0,1);")
        self.emit("csr(16,1,32'h1fe,0,0);csr(16,0,0,0,0);")
        self.completion(59,code=1)
        self.submit(descriptor(mode=3,cookie=59))
        self.emit("csr_valid=1;csr_write=1;csr_addr=16;csr_wdata=2;"
                  "#1;if(csr_ready!==1) $fatal(1,\"W1C coincidence not accepted\");"
                  "tick;csr_valid=0;csr_rsp_ready=1;"
                  "if(csr_rsp_valid!==1 || csr_rdata!==0 || csr_error!==0)"
                  ' $fatal(1,"W1C response mismatch");'
                  "tick;csr_rsp_ready=0;csr(16,0,0,2,0);csr(16,1,2,0,0);")
        self.mark("new_error_wins_simultaneous_w1c")
        self.load(3,lock=1);self.load(3,code=3)
        self.emit("csr(8,0,0,143,0);")
        self.mark("locked_key_csr_permissions")
        bads = [
            (descriptor(mode=3),1),
            (descriptor(mode=0,data=b"x"),5),
            (descriptor(mode=1,aad=b"x"),1),
            (descriptor(first=0),4),
            (descriptor()[:-1]+b"\x01",1),
        ]
        for i,(desc,code) in enumerate(bads):
            self.completion(desc[56],code=code,final=(desc[1]&1))
            self.submit(desc);self.mark(f"malformed_{i}")
        for bad_count,bad_section in ((0,None),(2,None),(None,1),(17,None)):
            self.cookie=(self.cookie+1)&255
            self.completion(self.cookie,code=6)
            self.submit(descriptor(mode=1,data=b"x",cookie=self.cookie))
            self.beats(b"x",bad_count=bad_count,bad_section=bad_section)
            self.mark(f"stream_error_{bad_count}_{bad_section}")
        # Invalid continuation must preserve saved state; abort scrubs a suspended context.
        iv=self.data(12)
        self.completion(50,final=0)
        self.submit(descriptor(first=1,last=0,iv=iv,cookie=50))
        self.mark("suspend_for_abort")
        self.emit("csr(12,0,0,1,0);")
        self.completion(51,code=4,final=0)
        self.submit(descriptor(first=0,last=0,iv=bytes(12),cookie=51))
        self.mark("invalid_continuation_preserves")
        self.emit("csr(12,0,0,1,0);csr(20,1,0,0,0);csr(12,0,0,0,0);")
        self.mark("context_abort")
        self.completion(52,code=4)
        self.submit(descriptor(first=0,iv=iv,cookie=52))
        self.mark("aborted_context_rejected")

    def priority(self):
        # A held raw result publicly owns the nonpreemptive engine.
        plain=self.data(16)
        self.output(aes(self.keys[0],plain),mode=0,tid=231,gate=0)
        self.emit("random_ready=0;out_ready=0;completion_ready=0;tag_ready=0;")
        self.emit(f"raw({hexsv(plain)},0,231);while(!out_valid) tick;")
        jobs=[]
        # Enqueue order N0,H0,N1,H1; execution must be H0,H1,N0,N1.
        for index in range(4):
            cookie=230+index
            desc=descriptor(mode=1,ctx=index,slot=index,cookie=0,
                            status=0xA800+index*32,iv=self.data(12))
            jobs.append((desc,0x1000+index*0x100,cookie,index&1))
        for index in (1,3,0,2):
            desc,address,cookie,priority=jobs[index]
            self.completion(cookie,index)
            self.dma_job(desc,b"",b"",b"",bytes(16),addr=address,cookie=cookie,
                         priority=priority,enqueue=False)
        for desc,address,cookie,priority in jobs:
            self.emit(f"enqueue({address},{priority},{cookie});")
        self.emit("dma_priority=0;tick;if(dma_submit_ready!==0)"
                  ' $fatal(1,"normal queue did not fill");'
                  "dma_priority=1;tick;if(dma_submit_ready!==0)"
                  ' $fatal(1,"high queue did not fill");')
        self.emit("csr(20,1,0,0,1);")  # Held output/queued descriptors prevent abort.
        direct=descriptor(mode=1,ctx=3,cookie=245)
        self.completion(245,3)
        iv=self.data(12)
        _,tag=gcm(self.keys[0],iv,b"",b"")
        self.tags+=1;self.emit(f"expect_tag({hexsv(tag)},0,0,0);")
        raw_data=self.data(16)
        self.output(aes(self.keys[0],raw_data),mode=0,tid=233,gate=0)
        self.emit(f"task_descriptor={hexsv(direct,little=True)};task_valid=1;"
                  f"iv_in={hexsv(iv)};aad_bytes=0;payload_bytes=0;cmd_decrypt=0;"
                  "expected_tag=0;cmd_valid=1;"
                  f"in_block={hexsv(raw_data)};in_enc_dec=0;in_tag_id=233;in_valid=1;"
                  f"key_slot_id=0;key_in={hexsv(self.keys[0].ljust(32,bytes(1)))};"
                  "key_len_sel=0;key_lock=0;key_valid=1;key_result_ready=0;"
                  "out_ready=1;tick;out_ready=0;#1;"
                  "if(key_ready!==1 || task_ready!==0 || cmd_ready!==0 || in_ready!==0)"
                  ' $fatal(1,"idle key priority");'
                  "tick;key_valid=0;"
                  "if(key_result_valid!==1 || key_result_code!==0 || mem_req_valid!==0)"
                  ' $fatal(1,"key did not precede queued fetch");'
                  "key_result_ready=1;random_ready=1;tick;key_result_ready=0;"
                  "while(!task_ready) tick;"
                  "if(cmd_ready!==0 || in_ready!==0) $fatal(1,\"direct priority\");"
                  "tick;task_valid=0;while(!cmd_ready) tick;"
                  "if(in_ready!==0) $fatal(1,\"legacy command priority\");"
                  "tick;cmd_valid=0;while(!in_ready) tick;tick;in_valid=0;")
        self.mark("depth_two_priority_fifo_nonpreemption")

        # One queued job, then a second enqueue coincident with old-head selection.
        plain=self.data(16)
        self.output(aes(self.keys[0],plain),mode=0,tid=232,gate=0)
        self.emit("random_ready=0;out_ready=0;completion_ready=0;")
        self.emit(f"raw({hexsv(plain)},0,232);while(!out_valid) tick;")
        for index in range(2):
            desc=descriptor(mode=1,ctx=index,cookie=0,status=0xAA00+index*32)
            self.completion(240+index,index)
            self.dma_job(desc,b"",b"",b"",bytes(16),addr=0x1800+index*0x100,
                         cookie=240+index,priority=1,enqueue=False)
        self.emit("enqueue(32'h1800,1,240);out_ready=1;tick;out_ready=0;"
                  "dma_desc_addr=32'h1900;dma_priority=1;dma_cookie=241;dma_submit_valid=1;"
                  "if(out_valid!==0 || mem_req_valid!==0 || dma_submit_ready!==1 ||"
                  " outputs_seen!=outputs_added)"
                  ' $fatal(1,"simultaneous dequeue/enqueue precondition");'
                  "tick;dma_submit_valid=0;"
                  "if(mem_req_valid!==1 || mem_req_addr!==32'h1800)"
                  ' $fatal(1,"old-head selection did not coincide with enqueue");'
                  "simultaneous=simultaneous+1;"
                  "random_ready=1;")
        self.mark("simultaneous_queue_enqueue_dequeue")

    def memory_errors(self):
        # Fail each descriptor fetch beat without inventing a status destination.
        for index in range(4):
            cookie=80+index
            desc=descriptor(mode=1,cookie=0,status=0xAC00)
            self.put(0x2000,desc,True)
            self.emit("fetch_expected[fetch_added]=32'h2000;fetch_added=fetch_added+1;")
            self.completion(cookie,code=8,final=0)
            self.emit(f"fault_address={0x2000+16*index};fault_write=0;fault_skip=0;"
                      f"enqueue(32'h2000,0,{cookie});")
            self.mark(f"fetch_error_beat_{index}")
        for stage in ("aad","payload","output","status0","status1"):
            data=self.data(1);aad=self.data(1);iv=self.data(12)
            out,tag=gcm(self.keys[0],iv,aad,data)
            cookie=90+len(self.case_names)%10
            desc=descriptor(aad=aad,data=data,iv=iv,status=0xAC00)
            self.completion(cookie,code=8)
            self.put(0x2000,desc,True);self.put(0x4000,aad,True);self.put(0x6000,data,True)
            self.emit("fetch_expected[fetch_added]=32'h2000;fetch_added=fetch_added+1;")
            # Status reflects bytes already consumed; injected write errors are checked too.
            total=0 if stage in ("aad","payload") else 1
            status=struct.pack("<II",8,total)+bytes([cookie,0,1])+bytes(5)+bytes(16)
            if stage in ("output","status0","status1"):
                self.expect_write(0x8000,out)
            if stage in ("status0","status1"):
                # The first failed status request was formed before the error occurred.
                status=struct.pack("<II",0,1)+bytes([cookie,0,1])+bytes(5)+tag
            self.expect_write(0xAC00,status[:16])
            if stage!="status0":
                self.expect_write(0xAC10,status[16:])
            address={"aad":0x4000,"payload":0x6000,"output":0x8000,
                     "status0":0xAC00,"status1":0xAC10}[stage]
            self.emit(f"fault_address={address};fault_write={int(stage not in ('aad','payload'))};"
                      f"fault_skip=0;enqueue(32'h2000,0,{cookie});")
            self.mark(f"memory_error_{stage}")
            self.emit("csr(12,0,0,0,0);")
        self.fault_context_isolation()
        self.emit("csr(16,0,0,32'h17a,0);csr(16,1,32'h1fe,0,0);csr(16,0,0,0,0);")
        self.mark("sticky_errors_and_clear")

    def fault_context_isolation(self):
        sessions=[]
        for ctx in (1,2):
            iv=self.data(12);data=self.data(2)
            out,tag=gcm(self.keys[ctx],iv,b"",data,bool(ctx&1))
            sessions.append((ctx,iv,data,out,tag))
            self.completion(120+ctx,ctx,0,0)
            desc=descriptor(direction=ctx&1,ctx=ctx,slot=ctx,last=0,iv=iv,
                            data=data[:1],dst=0x8200+ctx*0x100,status=0xAE00)
            self.dma_job(desc,b"",data[:1],b"",bytes(16),final=0,total=1,cookie=120+ctx)
            self.mark(f"fault_isolation_suspend_{ctx}")
        self.emit("csr(12,0,0,6,0);")
        # A status fault after a consumed nonfinal first fragment must abort its context.
        data=self.data(1);iv=self.data(12)
        desc=descriptor(last=0,iv=iv,data=data,status=0xAE00)
        self.completion(123,code=8,final=0)
        self.put(0x2000,desc,True);self.put(0x6000,data,True)
        self.emit("fetch_expected[fetch_added]=32'h2000;fetch_added=fetch_added+1;")
        self.expect_write(0xAE00,struct.pack("<II",0,1)+bytes([123,0,0])+bytes(5))
        self.emit("fault_address=32'hae00;fault_write=1;fault_skip=0;enqueue(32'h2000,0,123);")
        self.mark("nonfinal_status_fault_aborts_consumed_only")
        self.emit("csr(12,0,0,6,0);")
        self.load(0)
        self.load(1,code=3)
        # Status delivery failure after an unconsumed invalid continuation must NOT abort it.
        ctx,iv,data,out,tag=sessions[0]
        desc=descriptor(direction=1,ctx=1,slot=1,first=0,last=0,
                        iv=bytes(x^1 for x in iv),status=0xAE00)
        self.completion(124,1,8,0)
        self.put(0x2000,desc,True)
        self.emit("fetch_expected[fetch_added]=32'h2000;fetch_added=fetch_added+1;")
        self.expect_write(0xAE00,struct.pack("<II",4,1)+bytes([124,1,0])+bytes(5))
        self.emit("fault_address=32'hae00;fault_write=1;fault_skip=0;enqueue(32'h2000,0,124);")
        self.mark("invalid_continuation_status_fault_preserves_context")
        self.emit("csr(12,0,0,6,0);")
        self.completion(125,1,tag=tag)
        desc=descriptor(direction=1,ctx=1,slot=1,first=0,iv=iv,data=data[1:],tag=tag,
                        dst=0x8380,status=0xAE00)
        self.dma_job(desc,b"",data[1:],out[1:],tag,total=2,cookie=125,
                     retained=[(0x8300,out[:1])])
        self.mark("other_context_finalizes_after_status_faults")
        # An error after restoring a live context consumes/aborts that session.
        ctx,iv,data,out,tag=sessions[1]
        desc=descriptor(ctx=2,slot=2,first=0,iv=iv,data=data[1:],tag=tag,status=0xAE00)
        self.completion(126,2,8)
        self.put(0x2000,desc,True);self.put(0x6000,data[1:],True)
        self.emit("fetch_expected[fetch_added]=32'h2000;fetch_added=fetch_added+1;")
        self.expect_write(0xAE00,struct.pack("<II",8,1)+bytes([126,2,1])+bytes(5)+bytes(16))
        self.emit("fault_address=32'h6000;fault_write=0;fault_skip=0;enqueue(32'h2000,0,126);")
        self.mark("live_continuation_read_fault_aborts")
        self.emit("csr(12,0,0,0,0);")

    def dma_invalid(self):
        for address in (0x2001,0xFFFFFFD0):
            self.completion(70,code=1,final=0)
            self.emit(f"enqueue(32'h{address:x},0,70);")
            self.mark(f"dma_bad_descriptor_address_{address:x}")
        # Invalid accessed ranges and forbidden overlaps must be rejected before writes.
        invalids=[
            (dict(src=0xFFFFFFFF,data=b"xx"),True,"source_wrap"),
            (dict(dst=0xFFFFFFFF,data=b"xx"),True,"destination_wrap"),
            (dict(aa=0xFFFFFFFF,aad=b"xx"),True,"aad_wrap"),
            (dict(src=0x6000,dst=0x6001,data=b"xx"),True,"partial_overlap"),
            (dict(aa=0x8000,aad=b"x",dst=0x8000,data=b"x"),True,"aad_output_overlap"),
            (dict(src=0x2000,data=b"x"),True,"descriptor_input_overlap"),
            (dict(dst=0x2000,data=b"x"),True,"descriptor_output_overlap"),
            (dict(status=0xA001),False,"status_alignment"),
            (dict(status=0xFFFFFFF0),False,"status_wrap"),
            (dict(status=0x6000,src=0x6000,data=b"x"),False,"status_input_overlap"),
            (dict(status=0x8000,dst=0x8000,data=b"x"),False,"status_output_overlap"),
        ]
        for options,safe,name in invalids:
            desc=descriptor(**options)
            self.completion(73,code=1)
            self.put(0x2000,desc,True)
            self.emit("fetch_expected[fetch_added]=32'h2000;fetch_added=fetch_added+1;")
            if safe:
                self.expect_write(0xA000,struct.pack("<II",1,0)+bytes([73,0,1])+bytes(5)+bytes(16))
            self.emit("enqueue(32'h2000,0,73);")
            self.mark(f"dma_invalid_{name}")

    def reset_active(self):
        for ctx in range(4):
            self.completion(130+ctx,ctx,0,0)
            self.submit(descriptor(ctx=ctx,slot=ctx,last=0,aad=b"a",data=b"b",
                                   iv=self.data(12),cookie=130+ctx))
            self.beats(b"a",1);self.beats(b"b")
            self.mark(f"reset_epoch_saved_context_{ctx}")
        self.emit("csr(12,0,0,15,0);")
        # Cancel DMA with accepted but unreturned descriptor read; memory agent discards it.
        desc=descriptor(mode=1,data=b"x")
        self.put(0x2000,desc,True)
        self.emit("hold_response=1;enqueue(32'h2000,0,71);while(!pending) tick;"
                  "reset_device;hold_response=0;"
                  "csr(8,0,0,0,0);csr(12,0,0,0,0);")
        for slot in range(4):
            self.load(slot)
        self.mark("reset_outstanding_dma")
        # Cancel a held raw output, then prove no stale result and slot0 invalid.
        data=self.data(16)
        self.output(aes(self.keys[0],data),mode=0,tid=72,gate=0)
        self.emit("random_ready=0;out_ready=0;")
        self.emit(f"raw({hexsv(data)},0,72);while(!out_valid) tick;repeat(4) tick;")
        self.emit("reset_device;outputs_added=outputs_added-1;"
                  "canceled_outputs=canceled_outputs+1;random_ready=1;csr(8,0,0,0,0);")
        for slot in range(4):
            self.load(slot)
        self.mark("reset_stalled_output")
        # No final input is supplied: reset cancels an active session, not a completion.
        self.submit(descriptor(aad=b"x",data=b"y"))
        self.beats(b"x",1)
        self.emit("repeat(5) tick;reset_device;csr(12,0,0,0,0);")
        for slot in range(4):
            self.load(slot)
        self.direct(2,0,0,b"z",name="post_reset_no_stale_state")

    def text(self):
        return "\n".join(self.lines)+"\n"


def generate(capacity,seed,kind):
    cases=Cases(capacity,seed)
    if kind=="boundaries" and capacity==256:
        cases.initialize()
        cases.boundaries(maximum=True)
        cases.full_retention()
        return cases
    cases.basic()
    if kind!="smoke":
        cases.tag_bits()
        cases.boundaries()
        cases.interleave()
        cases.dma_modes()
        cases.interleave(dma=True)
        cases.full_retention()
        cases.errors()
        cases.dma_invalid()
        cases.priority()
        cases.memory_errors()
        cases.reset_active()
    return cases
