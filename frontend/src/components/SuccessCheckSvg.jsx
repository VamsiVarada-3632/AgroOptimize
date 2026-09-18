import React from 'react';

export default function SuccessCheckSvg({ className = "w-24 h-24" }) {
  return (
    <div className="flex items-center justify-center">
      <svg className={className} fill="none" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <circle 
          cx="50" 
          cy="50" 
          r="48" 
          stroke="#1F6B3A" 
          strokeDasharray="302" 
          strokeDashoffset="302" 
          strokeWidth="4"
        >
          <animate 
            attributeName="stroke-dashoffset" 
            dur="0.6s" 
            fill="freeze" 
            from="302" 
            to="0" 
          />
        </circle>
        <path 
          d="M30 50L45 65L70 35" 
          stroke="#1F6B3A" 
          strokeDasharray="60" 
          strokeDashoffset="60" 
          strokeLinecap="round" 
          strokeLinejoin="round" 
          strokeWidth="6"
        >
          <animate 
            attributeName="stroke-dashoffset" 
            begin="0.6s" 
            dur="0.4s" 
            fill="freeze" 
            from="60" 
            to="0" 
          />
        </path>
      </svg>
    </div>
  );
}
