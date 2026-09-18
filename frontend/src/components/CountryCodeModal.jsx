import React, { useState } from 'react';

const countries = [
  { flag: '🇮🇳', name: 'India', code: '+91' },
  { flag: '🇺🇸', name: 'United States', code: '+1' },
  { flag: '🇨🇦', name: 'Canada', code: '+1' },
  { flag: '🇬🇧', name: 'United Kingdom', code: '+44' },
  { flag: '🇦🇺', name: 'Australia', code: '+61' },
  { flag: '🇩🇪', name: 'Germany', code: '+49' },
  { flag: '🇫🇷', name: 'France', code: '+33' },
  { flag: '🇧🇷', name: 'Brazil', code: '+55' },
  { flag: '🇯🇵', name: 'Japan', code: '+81' },
  { flag: '🇿🇦', name: 'South Africa', code: '+27' },
];

export default function CountryCodeModal({ isOpen, onClose, onSelect, selectedCode = "+91" }) {
  const [searchTerm, setSearchTerm] = useState('');

  if (!isOpen) return null;

  const filteredCountries = countries.filter(c => 
    c.name.toLowerCase().includes(searchTerm.toLowerCase()) || 
    c.code.includes(searchTerm)
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 backdrop-blur-sm p-4 animate-[fadeIn_0.2s_ease-out]">
      {/* Modal Card */}
      <div className="bg-surface-container-lowest w-full max-w-md rounded-xl shadow-ambient flex flex-col max-h-[85vh] overflow-hidden transform scale-100 opacity-100 transition-all">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-surface-variant">
          <h2 className="font-headline-md text-headline-md text-primary m-0">Select Country</h2>
          <button 
            onClick={onClose}
            aria-label="Close modal" 
            className="w-12 h-12 flex items-center justify-center text-on-surface-variant hover:text-primary hover:bg-surface-container-low rounded-full transition-colors flex-shrink-0"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
        
        {/* Search Bar Area */}
        <div className="p-4 bg-surface-bright border-b border-surface-variant">
          <div className="relative flex items-center w-full">
            <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
              <span className="material-symbols-outlined text-on-surface-variant">search</span>
            </div>
            <input 
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              aria-label="Search countries" 
              className="block w-full pl-10 pr-3 py-3 border border-outline-variant rounded-lg bg-surface-container-lowest placeholder-on-surface-variant focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary sm:text-sm font-body-md transition-shadow min-h-[48px]" 
              placeholder="Search countries..." 
              type="text"
            />
          </div>
        </div>

        {/* Scrollable Country List */}
        <div className="flex-1 overflow-y-auto custom-scrollbar p-2">
          <ul className="space-y-1" role="listbox">
            {filteredCountries.map((c, idx) => {
              const isSelected = c.code === selectedCode && countries.find(x => x.code === selectedCode)?.name === c.name;
              return (
                <li 
                  key={idx}
                  onClick={() => {
                    onSelect(c);
                    onClose();
                  }}
                  aria-selected={isSelected} 
                  className={`flex items-center justify-between p-3 rounded-lg cursor-pointer min-h-[48px] transition-colors ${
                    isSelected 
                      ? 'bg-primary-fixed/30 hover:bg-primary-fixed/40' 
                      : 'hover:bg-surface-container-low'
                  }`}
                  role="option"
                >
                  <div className="flex items-center space-x-4">
                    <span aria-hidden="true" className="text-2xl">{c.flag}</span>
                    <span className="font-label-md text-label-md text-on-surface">{c.name}</span>
                  </div>
                  <div className="flex items-center space-x-3">
                    <span className="font-body-md text-body-md text-on-surface-variant">{c.code}</span>
                    {isSelected && (
                      <span 
                        className="material-symbols-outlined text-primary" 
                        style={{ fontVariationSettings: "'FILL' 1" }}
                      >
                        check
                      </span>
                    )}
                  </div>
                </li>
              );
            })}
            {filteredCountries.length === 0 && (
              <li className="text-center text-on-surface-variant p-4">No countries found</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
