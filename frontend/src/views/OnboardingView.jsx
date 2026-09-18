import React, { useState, useEffect, useRef } from 'react';
import ParticleBackground from '../components/ParticleBackground';

const slides = [
  {
    image: 'https://lh3.googleusercontent.com/aida-public/AB6AXuApUFXuy_iPGjAupPkYfl0BPTtyX79ec5cREamw-iKmLePRwEzNmIqWyC18jULC5wOISgJ2_lIgRCne5VgjdsCu9oAXS2uiXEnW5DH-uIW7loCiPHp_a6cOSmuWMwh4Z7kZB5TzKwQjP-QhsbEwEC3U5N7qg1okI-Y0-yIERaPu72BmnUpD1uzQImB0keIqYvNV9vdmHm8PuSvG2OKFfs80k3qkWVfEGiwFSqHgt2F6fRryRs5eqvC8',
    title: 'Plan smarter, farm better',
    description: 'Data-driven insights tailored to your specific fields, helping you make decisions with confidence.'
  },
  {
    image: 'https://lh3.googleusercontent.com/aida-public/AB6AXuA3mcjUiOUreic51sPLvc1BmyYNnP1oisLuUM9j6peSmGXQuFNtAZJ2cIfoBFUOLYXwm1AJvnYyNdCTz3rWua1Vf05HtqYiY3WYntKdTBKfPo_CscLGiHtmY6m-5N9Gy1IXHUlee4WAsuADtwu-3R-1ERv5eqqlK7Nz92wlR-4vuNj5gDtQaHLdCmwx-nx926Y79hSEzOOUG0IYwaYx3U26F5bLCNhiaJs_E5-uvfud0s3DO1NOyB44',
    title: 'We handle the uncertainty',
    description: 'Our advanced logic turns unpredictable weather and market data into reliable, actionable plans.'
  },
  {
    isCustom: true,
    title: 'Plans that fit your goals',
    description: 'Optimize for what matters most to your operation this season.'
  },
  {
    isAction: true,
    title: 'Ready to grow?'
  }
];

export default function OnboardingView({ onNavigate, selectedLanguage, onChangeLanguage }) {
  const [showSplash, setShowSplash] = useState(true);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const sliderRef = useRef(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      setShowSplash(false);
    }, 2000); // 2 seconds splash for better feel, matching style of code.html
    return () => clearTimeout(timer);
  }, []);

  const handleScroll = () => {
    if (!sliderRef.current) return;
    const scrollLeft = sliderRef.current.scrollLeft;
    const slideWidth = sliderRef.current.clientWidth;
    const newSlide = Math.round(scrollLeft / slideWidth);
    if (newSlide !== currentSlide && newSlide >= 0 && newSlide < slides.length) {
      setCurrentSlide(newSlide);
    }
  };

  const goToSlide = (idx) => {
    if (!sliderRef.current) return;
    const slideWidth = sliderRef.current.clientWidth;
    sliderRef.current.scrollTo({
      left: idx * slideWidth,
      behavior: 'smooth'
    });
    setCurrentSlide(idx);
  };

  const handleNext = () => {
    if (currentSlide < slides.length - 1) {
      goToSlide(currentSlide + 1);
    }
  };

  const handleSkip = () => {
    goToSlide(slides.length - 1);
  };

  return (
    <div className="bg-background text-on-background font-body-md min-h-screen flex flex-col overflow-hidden relative">
      <ParticleBackground />

      {/* Splash Screen Overlay */}
      {showSplash && (
        <div className="flex flex-col items-center justify-center w-full h-full absolute inset-0 bg-background z-30 transition-opacity duration-500">
          <img 
            alt="AgroOptimize Logo" 
            className="w-32 h-32 md:w-48 md:h-48 mb-6 object-contain fade-in" 
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuAfHQj8K3STkpCK4V9BuRp9K-Xljc-I1IWfqZg3RJd4Pb83CRnmOrwzq5YvWYgSTr1Fr1t_86XS1mo3w4Yh2vM0noIiJe43zlDhONebdnRowgXVeT1ecDV4h_HX32wXazvfnQ5_-0uoZILfnfaRiaBRRkeJkNjlt3XLoatB_xHdJlxw16iz5rwNEwy52TFgYlE_YyE5_aTMONagpYeJ94v4G8GY2xdJVcbgDhEy6xEQs1mV_X7KmyVJ"
          />
          <div className="inline-block border-r-2 border-primary pr-1">
            <h1 className="font-headline-lg-mobile md:font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary typewriter-effect">AgroOptimize</h1>
          </div>
          <p className="font-body-lg text-body-lg text-on-surface-variant mt-4 fade-in" style={{ animationDelay: '0.8s' }}>
            Your Digital Agronomist
          </p>
        </div>
      )}

      {/* Top Navigation */}
      {!showSplash && (
        <div className="absolute top-0 w-full flex justify-between items-center px-4 md:px-8 py-4 z-20">
          <div className="relative">
            <button 
              onClick={() => setLangMenuOpen(!langMenuOpen)}
              className="text-on-surface-variant font-label-md text-label-md hover:text-primary transition-colors flex items-center gap-1 min-h-[48px]"
            >
              <span className="material-symbols-outlined" style={{ fontSize: '18px' }}>language</span>
              {selectedLanguage === 'en' ? 'English' : selectedLanguage === 'hi' ? 'हिन्दी' : 'Language'}
            </button>
            
            {langMenuOpen && (
              <div className="absolute left-0 mt-2 w-36 bg-surface-container-lowest border border-outline-variant rounded-lg shadow-ambient z-50">
                <button 
                  onClick={() => { onChangeLanguage('en'); setLangMenuOpen(false); }}
                  className={`w-full text-left px-4 py-2 hover:bg-surface-container-low font-label-sm text-label-sm ${selectedLanguage === 'en' ? 'text-primary font-bold' : 'text-on-surface'}`}
                >
                  English
                </button>
                <button 
                  onClick={() => { onChangeLanguage('hi'); setLangMenuOpen(false); }}
                  className={`w-full text-left px-4 py-2 hover:bg-surface-container-low font-label-sm text-label-sm ${selectedLanguage === 'hi' ? 'text-primary font-bold' : 'text-on-surface'}`}
                >
                  हिन्दी
                </button>
              </div>
            )}
          </div>
          
          {currentSlide < slides.length - 1 && (
            <button 
              onClick={handleSkip}
              className="text-on-surface-variant font-label-md text-label-md hover:text-primary transition-colors h-[48px] px-4 rounded-full hover:bg-surface-container"
            >
              Skip
            </button>
          )}
        </div>
      )}

      {/* Main Content Area */}
      {!showSplash && (
        <main className="flex-grow flex flex-col justify-center items-center relative z-10 w-full max-w-lg mx-auto h-screen px-4">
          <div className="w-full h-full flex flex-col pt-20 pb-10">
            <div 
              ref={sliderRef}
              onScroll={handleScroll}
              className="carousel-container flex w-full h-full flex-grow relative"
            >
              {slides.map((slide, idx) => (
                <div 
                  key={idx} 
                  className="carousel-slide flex-shrink-0 w-full h-full flex flex-col items-center justify-center text-center px-4"
                >
                  {slide.isCustom ? (
                    <div className="w-full max-w-sm mb-8 bg-surface-container-lowest rounded-xl p-6 shadow-sm border border-surface-variant">
                      <div className="flex justify-around mb-6">
                        <div className="flex flex-col items-center">
                          <div className="w-12 h-12 rounded-full bg-primary-fixed/20 flex items-center justify-center mb-2 text-primary">
                            <span className="material-symbols-outlined">trending_up</span>
                          </div>
                          <span className="font-label-sm text-label-sm text-on-surface">Yield</span>
                        </div>
                        <div className="flex flex-col items-center">
                          <div className="w-12 h-12 rounded-full bg-primary-fixed/20 flex items-center justify-center mb-2 text-primary">
                            <span className="material-symbols-outlined">payments</span>
                          </div>
                          <span className="font-label-sm text-label-sm text-on-surface">Cost</span>
                        </div>
                        <div className="flex flex-col items-center">
                          <div className="w-12 h-12 rounded-full bg-primary-fixed/20 flex items-center justify-center mb-2 text-primary">
                            <span className="material-symbols-outlined">water_drop</span>
                          </div>
                          <span className="font-label-sm text-label-sm text-on-surface">Water</span>
                        </div>
                      </div>
                      <div className="bg-surface-container-low p-1 rounded-lg flex text-center">
                        <div className="flex-1 py-2 bg-surface-container-lowest rounded shadow-sm font-label-md text-label-md text-primary">Balanced</div>
                        <div className="flex-1 py-2 font-label-md text-label-md text-on-surface-variant">Max Yield</div>
                        <div className="flex-1 py-2 font-label-md text-label-md text-on-surface-variant">Safe</div>
                      </div>
                    </div>
                  ) : slide.isAction ? (
                    <div className="flex flex-col items-center">
                      <img 
                        alt="AgroOptimize Logo" 
                        className="w-24 h-24 mb-8 object-contain" 
                        src="https://lh3.googleusercontent.com/aida-public/AB6AXuAfHQj8K3STkpCK4V9BuRp9K-Xljc-I1IWfqZg3RJd4Pb83CRnmOrwzq5YvWYgSTr1Fr1t_86XS1mo3w4Yh2vM0noIiJe43zlDhONebdnRowgXVeT1ecDV4h_HX32wXazvfnQ5_-0uoZILfnfaRiaBRRkeJkNjlt3XLoatB_xHdJlxw16iz5rwNEwy52TFgYlE_YyE5_aTMONagpYeJ94v4G8GY2xdJVcbgDhEy6xEQs1mV_X7KmyVJ"
                      />
                    </div>
                  ) : (
                    <div 
                      className="bg-cover bg-center w-64 h-64 md:w-80 md:h-80 rounded-xl mb-8 shadow-sm bg-surface-container" 
                      style={{ backgroundImage: `url('${slide.image}')` }}
                    />
                  )}

                  <h2 className="font-headline-lg-mobile md:font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary mb-4">
                    {slide.title}
                  </h2>
                  
                  {slide.description && (
                    <p className="font-body-md text-body-md text-on-surface-variant max-w-sm">
                      {slide.description}
                    </p>
                  )}

                  {slide.isAction && (
                    <div className="w-full max-w-xs flex flex-col gap-4 mt-4">
                      <button 
                        onClick={() => onNavigate('register')}
                        className="w-full h-[48px] bg-primary text-on-primary rounded-full font-label-md text-label-md hover:opacity-90 transition-opacity shadow-sm flex items-center justify-center cursor-pointer"
                      >
                        Create Account
                      </button>
                      <button 
                        onClick={() => onNavigate('login')}
                        className="w-full h-[48px] bg-transparent border-2 border-primary text-primary rounded-full font-label-md text-label-md hover:bg-primary/5 transition-colors flex items-center justify-center cursor-pointer"
                      >
                        Log In
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Carousel Controls */}
            <div className="flex flex-col items-center justify-center mt-auto pb-4 gap-6">
              {/* Indicators */}
              <div className="flex gap-2">
                {slides.map((_, idx) => (
                  <div 
                    key={idx}
                    onClick={() => goToSlide(idx)}
                    className={`h-2 rounded-full cursor-pointer transition-all duration-300 ${
                      idx === currentSlide ? 'bg-primary w-4' : 'bg-outline-variant w-2'
                    }`}
                  />
                ))}
              </div>

              {/* Next Button */}
              {currentSlide < slides.length - 1 && (
                <button 
                  onClick={handleNext}
                  className="w-14 h-14 bg-primary text-on-primary rounded-full shadow-sm hover:opacity-90 transition-all flex items-center justify-center cursor-pointer"
                >
                  <span className="material-symbols-outlined">arrow_forward</span>
                </button>
              )}
            </div>
          </div>
        </main>
      )}
    </div>
  );
}
