import React from 'react';
import {AbsoluteFill, Composition, interpolate, registerRoot, useCurrentFrame} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {useGsapTimeline} from '@remotion/gsap';

const W=540, H=960, FPS=30, TOTAL=450;
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'};
const ease=(x)=>1-Math.pow(1-Math.max(0,Math.min(1,x)),3);
const lerp=(f,range,values)=>interpolate(f,range,values,clamp);
const steps=[
  {from:0,to:90,kicker:'BẢO MẬT TÀI SẢN SỐ',title:['VÍ LẠNH KÝ','GIAO DỊCH RA SAO?'],
    desc:'Khóa riêng được giữ bên trong ví cứng.',badge:'MÔ PHỎNG CƠ CHẾ KÝ'},
  {from:90,to:210,kicker:'BƯỚC 01  /  ỨNG DỤNG',title:['TẠO YÊU CẦU'],
    desc:'Điện thoại chuẩn bị lệnh gửi 0,01 ETH.',badge:'CHƯA KÝ'},
  {from:210,to:330,kicker:'BƯỚC 02  /  VÍ CỨNG',title:['KIỂM TRA & KÝ'],
    desc:'Kiểm tra số tiền, địa chỉ trên thiết bị rồi xác nhận.',badge:'KHÓA RIÊNG KHÔNG RỜI VÍ'},
  {from:330,to:450,kicker:'BƯỚC 03  /  MẠNG LƯỚI',title:['PHÁT GIAO DỊCH'],
    desc:'Ứng dụng gửi giao dịch đã ký lên blockchain.',badge:'ĐÃ KÝ  →  ĐÃ GỬI'},
];
const base={
  color:'#f6f8f4',fontFamily:'Arial, "Noto Sans", sans-serif',overflow:'hidden',
  background:'radial-gradient(ellipse at 50% 44%,#17384b 0%,#081923 43%,#040b14 89%)'
};
const BodyMaterial=()=> <meshPhysicalMaterial color="#253c48" metalness={.83} roughness={.21} clearcoat={1} />;
const GlassMaterial=()=> <meshPhysicalMaterial color="#183944" metalness={.54} roughness={.13} clearcoat={1} emissive="#0d3949" emissiveIntensity={.24}/>;

const Hardware=({frame,large=false})=>{
  const p=ease((frame-7)/28),t=frame/FPS;
  const turn=.08+Math.sin(t*.72)*.22;
  const s=large?1.15:1;
  return <group position={[0,Math.sin(t*1.5)*.065,0]} scale={Math.max(.001,p)*s} rotation={[.08,turn,-.06]}>
    <mesh><boxGeometry args={[2.25,3.48,.43]}/><BodyMaterial/></mesh>
    <mesh position={[0,.63,.231]}><boxGeometry args={[1.89,1.42,.035]}/><GlassMaterial/></mesh>
    <mesh position={[0,.63,.26]}><boxGeometry args={[1.32,.07,.025]}/><meshBasicMaterial color="#a2e5da"/></mesh>
    <mesh position={[0,.33,.26]}><boxGeometry args={[1.02,.045,.025]}/><meshBasicMaterial color="#579da3"/></mesh>
    <mesh position={[0,-.94,.24]}><cylinderGeometry args={[.35,.35,.055,48]}/><meshStandardMaterial color="#d4b38c" metalness={.84} roughness={.16}/></mesh>
    <mesh position={[0,-.94,.274]}><cylinderGeometry args={[.20,.20,.012,48]}/><meshBasicMaterial color="#263d4a"/></mesh>
    <mesh position={[0,-1.67,.18]}><boxGeometry args={[.63,.08,.17]}/><meshStandardMaterial color="#526e78" metalness={.6} roughness={.32}/></mesh>
    <mesh rotation={[1.12,0,t*.27]}><torusGeometry args={[2.24,.045,12,100]}/><meshStandardMaterial color="#e6c398" metalness={.83} roughness={.17}/></mesh>
    <mesh rotation={[-.45,.44,t*-.21]}><torusGeometry args={[2.0,.02,12,100]}/><meshBasicMaterial color="#85dfd3"/></mesh>
  </group>;
};
const Phone=({frame})=>{
  const p=ease((frame-90)/25);
  return <group position={[-.85,Math.sin(frame*.038)*.05,0]} rotation={[.04,-.22+frame*.001, .08]} scale={Math.max(.002,p)*.9}>
    <mesh><boxGeometry args={[2.17,3.90,.2]}/><meshStandardMaterial color="#859ba9" metalness={.87} roughness={.24}/></mesh>
    <mesh position={[0,0,.12]}><boxGeometry args={[2.01,3.70,.02]}/><meshStandardMaterial color="#08141c" metalness={.15} roughness={.25}/></mesh>
    <mesh position={[0,1.52,.14]}><boxGeometry args={[.51,.065,.024]}/><meshBasicMaterial color="#506573"/></mesh>
    <mesh position={[0,.55,.15]}><boxGeometry args={[1.56,.25,.03]}/><meshBasicMaterial color="#1e4b60"/></mesh>
    <mesh position={[0,.20,.15]}><boxGeometry args={[1.56,.25,.03]}/><meshBasicMaterial color="#245970"/></mesh>
    <mesh position={[0,-.49,.15]}><boxGeometry args={[1.56,.53,.03]}/><meshStandardMaterial color="#5ebbb0" emissive="#12746e" emissiveIntensity={.22}/></mesh>
    <mesh position={[0,-1.56,.14]}><boxGeometry args={[.54,.06,.02]}/><meshBasicMaterial color="#688893"/></mesh>
  </group>;
};
const Line=({a,b})=>{
  const dx=b[0]-a[0],dy=b[1]-a[1],d=Math.hypot(dx,dy);
  const angle=-Math.atan2(dx,dy);
  return <mesh position={[(a[0]+b[0])/2,(a[1]+b[1])/2,-.15]} rotation={[0,0,angle]}>
    <cylinderGeometry args={[.015,.015,d,8]}/>
    <meshBasicMaterial color="#4c9db4"/>
  </mesh>;
};
const points=[[-2.5,.4],[-1.45,1.48],[-.25,1.85],[1.15,1.45],[2.4,.48],[1.8,-1.09],[.25,-1.7],[-1.36,-1.08]];
const links=[[0,1],[1,2],[2,3],[3,4],[4,5],[5,6],[6,7],[7,0],[1,7],[2,6],[3,5]];
const Network=({frame})=>{
  const p=ease((frame-330)/28),t=(frame-330)/120;
  const spin=t*Math.PI*.43;
  const x=-2.5+5*Math.max(0,Math.min(1,t));
  return <group scale={Math.max(.002,p)} rotation={[.07,spin*.17,0]}>
    {links.map(([a,b],i)=><Line a={points[a]} b={points[b]} key={i}/>)}
    {points.map(([x,y],i)=><mesh key={i} position={[x,y,Math.sin(i*1.7)*.25]}>
      <sphereGeometry args={[.14+(i%3)*.025,16,12]}/>
      <meshStandardMaterial color={i%2?'#b4e9ea':'#e8c391'} metalness={.6} roughness={.22} emissive={i%2?'#327d96':'#926e2a'} emissiveIntensity={.55}/>
    </mesh>)}
    <mesh position={[x,Math.sin(t*Math.PI*2)*.16,.65]} rotation={[.2,t*6,.25]}>
      <octahedronGeometry args={[.38,0]}/>
      <meshStandardMaterial color="#b1f9e7" metalness={.6} roughness={.18} emissive="#35bba7" emissiveIntensity={.4}/>
    </mesh>
  </group>;
};
const Stage=({frame,step})=><div style={{
  position:'absolute',top:252,left:0,width:W,height:405,
  filter:'drop-shadow(0px 18px 38px #18b3ba44)'
}}>
  <ThreeCanvas width={W} height={405} style={{width:W,height:405,backgroundColor:'transparent'}}
    camera={{fov:47,position:[0,0,9.4]}}>
    <ambientLight intensity={.52}/>
    <hemisphereLight args={['#caedf4','#163243',1.25]}/>
    <directionalLight position={[-4,5,6]} color="#ffe8cb" intensity={3.8}/>
    <directionalLight position={[4,-2,3]} color="#5ddbd6" intensity={2.2}/>
    <pointLight position={[2,-4,-2]} intensity={39} color="#597dea" distance={13}/>
    {step===0&&<Hardware frame={frame} large/>}
    {step===1&&<><Phone frame={frame}/><mesh position={[1.6,.4,.24]} rotation={[.12,-.23,.17]} scale={Math.max(.002,ease((frame-108)/26))}>
      <boxGeometry args={[1.7,2.25,.18]}/><meshStandardMaterial color="#1c5966" metalness={.55} roughness={.23}/>
    </mesh></>}
    {step===2&&<Hardware frame={frame-210} large/>}
    {step===3&&<Network frame={frame}/>}
  </ThreeCanvas>
</div>;
const Subtitle=({label,detail})=><div style={{position:'absolute',top:694,left:36,right:36,textAlign:'center'}}>
  <div style={{display:'inline-block',maxWidth:470,padding:'12px 20px',border:'1px solid #89cfc363',
    borderRadius:24,background:'#123142aa',color:'#bff5e5',letterSpacing:2.2,fontSize:14,fontWeight:800}}>{label}</div>
  <div style={{marginTop:22,fontSize:24,fontWeight:600,lineHeight:1.34,color:'#e5eff0'}}>{detail}</div>
</div>;
const Content=()=> {
  const frame=useCurrentFrame();
  const index=frame<90?0:frame<210?1:frame<330?2:3;
  const item=steps[index];
  const local=frame-item.from;
  const fade=Math.min(1,local/9,(item.to-1-frame)/9);
  const intro=useGsapTimeline(({timeline,selector})=>{
    timeline.from(selector('[data-brand]'),{y:20,opacity:0,duration:.65,ease:'power2.out'},.08);
  });
  const headingSize=index===0?39:43;
  return <AbsoluteFill ref={intro} style={base}>
    <div style={{position:'absolute',top:49,left:35,right:35,height:1,background:'#86a6b64f'}}/>
    <div data-brand style={{position:'absolute',top:20,left:35,fontSize:14,fontWeight:800,letterSpacing:3.4}}>COLD / SIGN</div>
    <div style={{position:'absolute',top:24,right:35,fontSize:12,letterSpacing:2,color:'#91bfc1'}}>3D EXPLAINER</div>
    <div style={{position:'absolute',top:92,left:35,right:35,textAlign:'center',opacity:fade,transform:`translateY(${(1-fade)*15}px)`}}>
      <div style={{fontSize:13,fontWeight:800,letterSpacing:3,color:'#8adfd4'}}>{item.kicker}</div>
      <div style={{fontSize:headingSize,fontWeight:850,lineHeight:1.13,letterSpacing:-.9,marginTop:18}}>
        {item.title.map((line,i)=><div key={i}>{line}</div>)}
      </div>
    </div>
    <div style={{position:'absolute',top:258,left:55,right:55,height:350,
      background:'radial-gradient(ellipse,#3baea527 0%,transparent 70%)',filter:'blur(23px)'}}/>
    <Stage frame={frame} step={index}/>
    <div style={{opacity:fade}}><Subtitle label={item.badge} detail={item.desc}/></div>
    <div style={{position:'absolute',bottom:66,left:36,right:36,display:'flex',gap:9}}>
      {[1,2,3].map(i=><div key={i} style={{height:4,flex:1,background:i===index?'#d8bf97':i<index?'#6dc8ba':'#375866',borderRadius:8}}/>)}
    </div>
    <div style={{position:'absolute',bottom:30,left:36,fontSize:12,letterSpacing:2,color:'#9bb6bb'}}>KHÓA RIÊNG LUÔN Ở TRÊN VÍ CỨNG</div>
    <div style={{position:'absolute',bottom:30,right:36,fontSize:12,letterSpacing:2,color:'#9bb6bb'}}>{String(Math.min(3,index)).padStart(2,'0')}/03</div>
  </AbsoluteFill>;
};
registerRoot(()=><Composition id="WalletFlow" component={Content} durationInFrames={TOTAL} fps={FPS} width={W} height={H}/>);
