import React from 'react';
import {
  AbsoluteFill, Composition, interpolate, registerRoot, useCurrentFrame,
} from 'remotion';
import {ThreeCanvas} from '@remotion/three';
import {useGsapTimeline} from '@remotion/gsap';

const CLAMP = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};
const W = 540, H = 960;
const easeOut = (x) => 1 - Math.pow(1 - Math.min(1, Math.max(0, x)), 3);
const shared = {
  background: 'radial-gradient(circle at 50% 43%, #192f43 0%, #08131e 45%, #060c14 100%)',
  color: '#f6f7f2', fontFamily: 'Arial, Helvetica, sans-serif', overflow: 'hidden',
};
const hairline = {position:'absolute', top:63, left:40, right:40, height:1, background:'#9ab8c0', opacity:0.3};
const Header = () => <>
  <div style={hairline} />
  <div style={{position:'absolute',top:29,left:40,fontSize:16,fontWeight:700,letterSpacing:5}}>AETHER</div>
  <div style={{position:'absolute',top:31,right:40,fontSize:12,letterSpacing:2,color:'#a8c6cb'}}>STUDIO / 01</div>
</>;
const Footer = ({version}) => <>
  <div style={{position:'absolute',left:40,right:40,bottom:88,height:1,background:'#63818e',opacity:.35}}/>
  <div style={{position:'absolute',bottom:54,left:40,fontSize:12,letterSpacing:3,color:'#96b4c3'}}>MOTION STUDY / 2026</div>
  <div style={{position:'absolute',bottom:54,right:40,fontSize:12,letterSpacing:2,color:'#96b4c3'}}>{version}</div>
</>;
const Copy = ({kickerStyle={},headingStyle={},tagStyle={}}) => <>
  <div data-kicker style={{position:'absolute',top:155,left:40,right:40,textAlign:'center',fontSize:14,letterSpacing:7,fontWeight:700,color:'#9ee4da',...kickerStyle}}>DESIGN IN MOTION</div>
  <div data-heading style={{position:'absolute',top:655,left:25,right:25,textAlign:'center',fontSize:55,lineHeight:1.03,fontWeight:800,letterSpacing:-2,...headingStyle}}>MAKE SPACE<br/>FOR IDEAS.</div>
  <div data-tag style={{position:'absolute',top:796,left:40,right:40,textAlign:'center',fontSize:15,letterSpacing:2.4,color:'#bad0d4',...tagStyle}}>MOVE BEYOND THE FRAME</div>
</>;
const BaselineA = () => {
  const frame = useCurrentFrame();
  const reveal = easeOut((frame - 14) / 42);
  const rotation = frame * .47;
  const fade = interpolate(frame, [7, 29], [0, 1], CLAMP);
  const textY = interpolate(frame, [65, 95], [28, 0], CLAMP);
  const titleOpacity = interpolate(frame, [65, 95], [0, 1], CLAMP);
  return <AbsoluteFill style={shared}>
    <Header/>
    <div style={{position:'absolute',left:0,right:0,top:228,height:425,opacity:fade,transform:`scale(${0.75 + .25*reveal})`,transformOrigin:'center'}}>
      <div style={{position:'absolute',top:34,left:85,width:370,height:370,borderRadius:'50%',border:'2px solid #78baca',boxShadow:'0 0 40px #35a2d844'}}/>
      <div style={{position:'absolute',top:59,left:109,width:322,height:322,borderRadius:'50%',border:'1px solid #d7e4dc44',transform:`rotate(${rotation}deg)`}}>
        <div style={{position:'absolute',top:-10,left:149,width:19,height:19,background:'#b8f8e6',borderRadius:'50%',boxShadow:'0 0 24px #6cfad9'}}/>
      </div>
      <div style={{position:'absolute',top:86,left:139,width:263,height:263,borderRadius:60,background:'linear-gradient(135deg,#73dccf,#286883 46%,#142c49)',transform:`rotate(${-24 + 54*reveal}deg)`,boxShadow:'18px 25px 90px #39d9cf55',border:'2px solid #cce7e455'}}>
        <div style={{position:'absolute',inset:16,border:'1px solid #d1fff788',borderRadius:49}}/>
      </div>
    </div>
    <Copy
      kickerStyle={{opacity:fade,transform:`translateY(${(1-reveal)*20}px)`}}
      headingStyle={{opacity:titleOpacity,transform:`translateY(${textY}px)`}}
      tagStyle={{opacity:interpolate(frame,[95,120],[0,1],CLAMP)}}
    />
    <Footer version="A / REMOTION 2D"/>
  </AbsoluteFill>;
};
const Sculpture = () => {
  const frame = useCurrentFrame();
  const appear = easeOut((frame - 12) / 44);
  const spin = frame * 0.016;
  const bob = Math.sin(frame * .065) * .13;
  return <group position={[0, bob, 0]} scale={Math.max(.001, appear)}>
    <mesh rotation={[.37 + Math.sin(spin)*.16, spin*1.18, .13]}>
      <icosahedronGeometry args={[1.72, 1]}/>
      <meshPhysicalMaterial color="#5acfc9" metalness={.83} roughness={.17} clearcoat={1} clearcoatRoughness={.1}/>
    </mesh>
    <mesh rotation={[1.13, 0, -0.35 + spin*.6]}>
      <torusGeometry args={[2.46,.065,16,120]}/>
      <meshStandardMaterial color="#c8f5ed" metalness={.7} roughness={.2}/>
    </mesh>
    <mesh rotation={[.32, .45, .63-spin*.48]}>
      <torusGeometry args={[2.18,.02,12,120]}/>
      <meshStandardMaterial color="#73a8f3" emissive="#2b6fbd" emissiveIntensity={.5}/>
    </mesh>
  </group>;
};
const EnhancedB = () => {
  const scope = useGsapTimeline(({timeline,selector}) => {
    timeline.from(selector('[data-kicker]'),{y:25,opacity:0,duration:.75,ease:'power3.out'},.15)
      .from(selector('[data-heading]'),{y:38,opacity:0,duration:.9,ease:'power3.out'},2.0)
      .from(selector('[data-tag]'),{y:20,opacity:0,duration:.65,ease:'power2.out'},3.25);
  });
  return <AbsoluteFill ref={scope} style={shared}>
    <Header/>
    <div style={{position:'absolute',left:0,right:0,top:235,height:420,filter:'drop-shadow(0 25px 45px #24bfc144)'}}>
      <ThreeCanvas width={W} height={420} style={{width:W,height:420,backgroundColor:'transparent'}}
        camera={{fov:50,position:[0,0,8.5]}}>
        <ambientLight intensity={.7}/>
        <directionalLight color="#a8fff0" intensity={3} position={[-4,5,7]}/>
        <pointLight color="#4a76ff" intensity={65} position={[3,-3,4]} distance={12}/>
        <Sculpture/>
      </ThreeCanvas>
    </div>
    <Copy/>
    <Footer version="B / GSAP + THREE"/>
  </AbsoluteFill>;
};
const Root = () => <>
  <Composition id="MotionA" component={BaselineA} durationInFrames={180} fps={30} width={W} height={H}/>
  <Composition id="MotionB" component={EnhancedB} durationInFrames={180} fps={30} width={W} height={H}/>
</>;
registerRoot(Root);
