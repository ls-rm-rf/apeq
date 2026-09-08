// Standalone R1 validation; links the unchanged measured IPS-OLE core.
// Full replies are exposed only in this explicitly stripped experiment.
#include "ips_ole/core.h"
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace apeq::ips_ole;

struct Capture : Retriever {
  const std::vector<Fp>& offered;
  std::vector<std::size_t> choices;
  explicit Capture(const std::vector<Fp>& v) : offered(v) {}
  std::vector<Fp> retrieve(std::size_t, const std::vector<std::size_t>& c) override {
    choices=c; std::vector<Fp> out;
    for(auto i:c) out.push_back(offered[i]);
    return out;
  }
};
struct Recovery { Polynomial a,b; std::size_t usable; };
Recovery attack(const PublicPoints& points, const Encoding& encoding,
                const std::vector<Fp>& full_replies,
                const std::vector<std::size_t>& genuine, const OleParams& p) {
  const auto& theta=points.codeword_points();
  std::vector<Fp> gx,gv,gu;
  std::vector<bool> good(p.n,false);
  for(auto i:genuine) {
    good[i]=true; gx.push_back(theta[i]); gv.push_back(encoding.values[i]);
    gu.push_back(full_replies[i]);
  }
  // Both polynomials follow from the receiver's legitimate view.
  Polynomial s=interpolate(std::vector<Fp>(gx.begin(),gx.begin()+p.k),
                           std::vector<Fp>(gv.begin(),gv.begin()+p.k));
  Polynomial y=interpolate(gx,gu);
  std::vector<Fp> ax,av;
  for(std::size_t i=0;i<p.n;++i) if(!good[i]) {
    auto denominator=encoding.values[i]-evaluate(s,theta[i]);
    if(denominator.is_zero()) continue;
    ax.push_back(theta[i]);
    av.push_back((full_replies[i]-evaluate(y,theta[i]))*denominator.inv());
  }
  const auto usable=ax.size(), need=p.degree_a()+1;
  if(usable<need) throw std::runtime_error("insufficient effective noisy replies");
  ax.erase(ax.begin()+need,ax.end()); av.erase(av.begin()+need,av.end());
  auto a=interpolate(ax,av), product=multiply(a,s);
  Polynomial b=y;
  b.resize(std::max(b.size(),product.size()),Fp::zero());
  for(std::size_t i=0;i<product.size();++i) b[i]=b[i]-product[i];
  while(b.size()>1 && b.back().is_zero()) b.pop_back();
  return {a,b,usable};
}
void dump_view(const std::filesystem::path& path, const PublicPoints& points,
               const Encoding& encoding, const std::vector<Fp>& replies,
               const std::vector<std::size_t>& genuine) {
  std::ofstream f(path);
  f<<"index,theta_hex,encoding_hex,reply_hex,genuine\n";
  for(std::size_t i=0;i<encoding.values.size();++i)
    f<<i<<","<<points.codeword_points()[i].to_hex()<<","<<encoding.values[i].to_hex()
     <<","<<replies[i].to_hex()<<","<<(std::find(genuine.begin(),genuine.end(),i)!=genuine.end())<<"\n";
}
int main(int argc,char** argv) {
  if(argc!=2) return 2;
  const std::filesystem::path out=argv[1];
  std::filesystem::create_directories(out/"views");
  if(std::filesystem::exists(out/"r1-trials.csv")) throw std::runtime_error("refuse overwrite");
  std::ofstream csv(out/"r1-trials.csv");
  csv<<"bits,trial,n,ell,k,t,usable,needed,recovered_coordinates,polynomials_verified,zero_denominator_diagnostic,attack_ms\n";
  const auto p=OleParams::defaults();
  const auto master=deterministic_test_seed();
  for(int bits:{16,64}) for(int trial=0;trial<20;++trial) {
    const auto id=std::to_string(bits)+"-"+std::to_string(trial);
    auto pub=derive_key(master,"r1/public/"+id);
    auto recv=derive_key(master,"r1/receiver/"+id);
    auto send=derive_key(master,"r1/sender/"+id);
    Prng input(derive_key(master,"r1/inputs/"+id));
    std::vector<Fp> alpha,beta,w,b;
    for(std::size_t i=0;i<p.t;++i) {
      auto x=input.next_u64(),z=input.next_u64();
      if(bits==16){ x&=65535; z&=65535; }
      if(i%2==0) z=x;
      alpha.push_back(Fp::from_u64(x)); beta.push_back(Fp::from_u64(z));
      auto wi=input.random_fp(); while(wi.is_zero()) wi=input.random_fp();
      w.push_back(wi); b.push_back(Fp::zero()-wi*alpha.back());
    }
    OleReceiver receiver(p,pub,recv,1);
    OleSender sender(p,pub,send,1);
    const auto enc=receiver.encode(beta);
    const auto replies=sender.respond(enc,w,b);
    Capture capture(replies);
    const auto selected=receiver.retrieve(capture);
    const auto honest=receiver.reconstruct(selected);
    for(std::size_t i=0;i<p.t;++i)
      if(honest[i]!=w[i]*(beta[i]-alpha[i])) throw std::runtime_error("honest mismatch");
    auto begin=std::chrono::steady_clock::now();
    auto recovered=attack(receiver.public_points(),enc,replies,capture.choices,p);
    const double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
    std::size_t correct=0;
    for(std::size_t i=0;i<p.t;++i) {
      const auto& x=receiver.public_points().input_points()[i];
      auto a=evaluate(recovered.a,x),bv=evaluate(recovered.b,x);
      if(!a.is_zero() && (Fp::zero()-bv)*a.inv()==alpha[i]) ++correct;
    }
    // Independent verifier reconstructs the actual A and B pointwise using
    // two shadow sender calls with identical private randomness; never passed to attack().
    OleSender zero_sender(p,pub,send,1),one_sender(p,pub,send,1);
    Encoding zero{1,std::vector<Fp>(p.n,Fp::zero())};
    Encoding one{1,std::vector<Fp>(p.n,Fp::one())};
    auto actual_b=zero_sender.respond(zero,w,b);
    auto actual_ab=one_sender.respond(one,w,b);
    bool verified=degree(recovered.a)<=p.degree_a() && degree(recovered.b)<=p.degree_b();
    for(std::size_t i=0;i<p.n;++i) {
      auto x=receiver.public_points().codeword_points()[i];
      verified &= evaluate(recovered.a,x)==actual_ab[i]-actual_b[i];
      verified &= evaluate(recovered.b,x)==actual_b[i];
    }
    // One deterministic noisy ordinate is changed to a genuine-looking value:
    // attack must skip its zero denominator without changing recovery.
    auto boundary=enc; auto boundary_replies=replies;
    std::vector<Fp> sx,sv;
    for(std::size_t q=0;q<p.k;++q) {
      auto j=capture.choices[q]; sx.push_back(receiver.public_points().codeword_points()[j]); sv.push_back(enc.values[j]);
    }
    auto sp=interpolate(sx,sv);
    for(std::size_t j=0;j<p.n;++j) if(std::find(capture.choices.begin(),capture.choices.end(),j)==capture.choices.end()) {
      auto x=receiver.public_points().codeword_points()[j];
      boundary.values[j]=evaluate(sp,x);
      boundary_replies[j]=actual_b[j]+(actual_ab[j]-actual_b[j])*boundary.values[j];
      break;
    }
    auto bd=attack(receiver.public_points(),boundary,boundary_replies,capture.choices,p);
    bool bdok=bd.a==recovered.a && bd.b==recovered.b && bd.usable+1==recovered.usable;
    dump_view(out/"views"/(id+".csv"),receiver.public_points(),enc,replies,capture.choices);
    csv<<bits<<","<<trial<<","<<p.n<<","<<p.ell<<","<<p.k<<","<<p.t<<","<<recovered.usable<<","<<p.degree_a()+1
       <<","<<correct<<","<<verified<<","<<bdok<<","<<ms<<"\n"; csv.flush();
    if(correct!=p.t || !verified || !bdok) throw std::runtime_error("R1 validation failed: "+id);
    std::cout<<id<<" recovered="<<correct<<" usable="<<recovered.usable<<" attack_ms="<<ms<<std::endl;
  }
}

