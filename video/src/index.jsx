import React from 'react';
import {
  AbsoluteFill,
  Composition,
  interpolate,
  registerRoot,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'};

const PalmMotion = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const p = interpolate(frame, [0, durationInFrames - 1], [0, 1], clamp);
  const cameraScale = 1 + 0.13 * p;
  const waterShift = -180 * p;
  const islandY = 36 * p;
  const skylineY = 10 * p;

  return (
    <AbsoluteFill style={{background: '#0d4660', overflow: 'hidden'}}>
      <div style={{
        position: 'absolute', inset: 0,
        background: 'linear-gradient(180deg,#f2b36d 0%,#9ec7d5 36%,#1c7188 37%,#0b5268 100%)'
      }}/>

      <div style={{position:'absolute',left:0,right:0,top:250,height:150,transform:`translateY(${skylineY}px)`,opacity:0.78}}>
        {Array.from({length:34}).map((_,i)=><div key={i} style={{
          position:'absolute',bottom:0,left:`${i*3.1}%`,width:18+(i%5)*8,height:45+(i%7)*18,
          background:'#6d7780',opacity:0.65,borderRadius:'3px 3px 0 0'
        }}/>) }
      </div>

      <div style={{position:'absolute',left:-220,right:-220,bottom:-80,height:590,transform:`translateX(${waterShift}px)`,opacity:0.28,
        background:'repeating-linear-gradient(168deg,rgba(255,255,255,.35) 0 3px,transparent 3px 38px)'}}/>

      <div style={{position:'absolute',left:'50%',top:'54%',width:1550,height:720,
        transform:`translate(-50%,-50%) scale(${cameraScale}) translateY(${islandY}px)`,transformOrigin:'50% 52%'}}>
        <div style={{position:'absolute',left:'50%',top:70,width:115,height:570,transform:'translateX(-50%)',background:'#d8c39a',borderRadius:55}}/>
        {[-1,1].map(side => Array.from({length:8}).map((_,i)=>{
          const y=95+i*62;
          const rot=side*(21+i*1.2);
          return <div key={`${side}-${i}`} style={{position:'absolute',left:'50%',top:y,width:560,height:68,
            transformOrigin:side<0?'100% 50%':'0% 50%',
            transform:`translateX(${side<0?-560:0}px) rotate(${rot}deg)`,
            background:'#d8c39a',borderRadius:40}}/>;
        }))}
        <div style={{position:'absolute',left:'50%',top:-110,width:1360,height:790,transform:'translateX(-50%)',border:'52px solid #b8a783',borderRadius:'50%',opacity:0.95}}/>
      </div>

      <div style={{position:'absolute',left:70,bottom:55,fontFamily:'Arial, sans-serif',color:'white',fontSize:28,letterSpacing:5,opacity:0.82}}>
        RUNNER-3 · REMOTION MOTION TEST
      </div>
    </AbsoluteFill>
  );
};

const Root = () => (
  <Composition
    id="PalmMotion"
    component={PalmMotion}
    durationInFrames={180}
    fps={30}
    width={1920}
    height={1080}
  />
);

registerRoot(Root);
