import React from 'react';
import {Composition, AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';

// 설치 확인용 2초 테스트 (팬 클립 렌더 연결은 별도 작업)
const Hello: React.FC<{text: string}> = ({text}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const pop = spring({frame, fps, config: {damping: 12}});
  return (
    <AbsoluteFill style={{background: '#0e0e10', justifyContent: 'center', alignItems: 'center'}}>
      <div style={{color: '#ff6fb5', fontSize: 96, fontWeight: 800, transform: `scale(${pop})`,
                   opacity: interpolate(frame, [0, 10], [0, 1], {extrapolateRight: 'clamp'})}}>{text}</div>
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => (
  <Composition id="Hello" component={Hello} durationInFrames={60} fps={30} width={1080} height={1920}
               defaultProps={{text: '설치 확인'}} />
);
