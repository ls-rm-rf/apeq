"""Generate synthetic results.csv files: one clean, several with the exact
defects the validator is supposed to catch."""
import csv, uuid, random, math, sys
HEADER=["run_id","timestamp_utc","git_commit","hostname","protocol","backend","variant",
"batch_size","input_bits","field_bits","security_param","network","rtt_ms","bandwidth_mbps",
"rep","seed","party","setup_ms","online_ms","total_ms","setup_bytes_sent","setup_bytes_recv",
"online_bytes_sent","online_bytes_recv","bytes_sent","bytes_recv",
"peak_rss_kb","n_ot","n_field_ops","correct","n_false_pos","n_false_neg","status","note"]
rnd=random.Random(1)

def apeq_bytes(batch, fb):
    n,t=1024,48; g=math.ceil(batch/t); return g*n*math.ceil(fb/8)

def mkrun(proto,variant,backend,batch,ib,fb,net,rep,rid=None,inflate=1.0,ok=True,
          rtt=0.5,bw=1000,time_offset=0.0):
    rid=rid or str(uuid.uuid4())
    if proto=="apeq" and variant=="ole":
        sent_b=apeq_bytes(batch,fb); sent_a=apeq_bytes(batch,fb)
    else:
        sent_b=batch*ib*8; sent_a=batch*ib*16
    sent_b=int(sent_b*inflate); sent_a=int(sent_a*inflate)
    setup=150.0+rnd.uniform(-3,3)+time_offset
    online=0.02*batch+rnd.uniform(0,0.5)+time_offset
    seed=rnd.getrandbits(63)
    rows=[]
    for party in ("A","B"):
        s=sent_a if party=="A" else sent_b
        r=sent_b if party=="A" else sent_a
        setup_s=min(s,128); setup_r=min(r,128)
        rows.append([rid,"2026-08-25T10:00:00Z","abc1234","host1",proto,backend,variant,
            batch,ib,fb,128,net,rtt,bw,rep,seed,party,
            f"{setup:.3f}",f"{online:.3f}",f"{setup+online:.3f}",
            setup_s,setup_r,s-setup_s,r-setup_r,s,r,
            40000,0,-1,"true" if ok else "false",
            -1 if party=="A" else 0, -1 if party=="A" else 0,"ok",""])
    return rows

def write(path,rows):
    with open(path,"w",newline="") as f:
        w=csv.writer(f); w.writerow(HEADER); w.writerows(rows)

# --- clean dataset ---
clean=[]
for batch in [1,10,100,1000]:
    for rep in range(10):
        clean+=mkrun("apeq","ole","ips_ole",batch,32,127,"lan",rep)
write("synth_clean.csv",clean)

# --- defect 1: the 67-bit communication figure ---
bad1=list(clean)
bad1+=mkrun("apeq","ole","ips_ole",10000,32,127,"lan",0,inflate=0.001)
write("synth_bad_comm.csv",bad1)

# --- defect 2: batch 10 and batch 100 rows byte-identical ---
bad2=[]
for batch in [10,100]:
    rnd.seed(42)
    for rep in range(10):
        bad2+=mkrun("emp_eq","n/a","n/a",batch,32,128,"lan",rep)
write("synth_dup_rows.csv",bad2)

# --- defect 3: unpaired run + mismatched byte counters ---
bad3=list(clean)
orphan=mkrun("apeq","ole","ips_ole",10,32,127,"lan",0)[0]
bad3.append(orphan)
mism=mkrun("apeq","ole","ips_ole",100,32,127,"wan",0)
mism[1][24]=str(int(mism[1][24])+99999)   # B.bytes_sent perturbed
bad3+=mism
write("synth_mismatch.csv",bad3)

# --- defect 4: apeq/ole reporting a false accept (contradicts Thm 5.1) ---
bad4=list(clean)
fa=mkrun("apeq","ole","ips_ole",1000,64,127,"lan",0)
fa[1][30]="3"    # n_false_pos on party B
fa[1][29]="false"
bad4+=fa
write("synth_falsepos.csv",bad4)

# --- defect 5: communication decreasing with batch size ---
bad5=[]
for batch,infl in [(100,1.0),(1000,0.5)]:
    for rep in range(10):
        bad5+=mkrun("apeq","ole","ips_ole",batch,32,127,"lan",rep,inflate=infl)
write("synth_nonmono.csv",bad5)

# --- round-sweep dataset with known setup/online slopes 2 and 3 ---
rounds=[]
for rtt in [0.5,20,40,80]:
    for rep in range(3):
        pair=mkrun("emp_eq","n/a","n/a",100,32,128,"round_sweep",rep,
                   rtt=rtt,time_offset=0.0)
        # Override the noisy synthetic timings with an exact affine model.
        for row in pair:
            row[17]=f"{10+2*rtt:.3f}"
            row[18]=f"{5+3*rtt:.3f}"
            row[19]=f"{15+5*rtt:.3f}"
        rounds+=pair
write("synth_rounds.csv",rounds)
print("written")
