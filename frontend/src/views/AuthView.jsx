import React, { useState, useEffect, useMemo, useRef } from 'react';
import CountryCodeModal from '../components/CountryCodeModal';
import { api, DISTRICTS } from '../services/api';

// Small fallback crop list, used only if GET /api/catalog is unreachable --
// kept in sync with the same fallback in SettingsView.jsx / ProfileSetupView.jsx.
const FALLBACK_CROPS = ['Sugarcane', 'Wheat', 'Paddy', 'Maize', 'Cotton', 'Groundnut', 'Sorghum', 'Tapioca'];

export default function AuthView({ initialMode = 'login', onSuccess, selectedLanguage }) {
  const [subView, setSubView] = useState(initialMode === 'register' ? 'register-1' : initialMode); // 'login' | 'register-1' | 'register-2' | 'otp'
  const [loginTab, setLoginTab] = useState('phone'); // 'phone' | 'email'

  // Input states
  const [fullName, setFullName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [emailAddress, setEmailAddress] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const [country, setCountry] = useState({ flag: '🇮🇳', name: 'India', code: '+91' });
  const [countryModalOpen, setCountryModalOpen] = useState(false);

  // Signup step 2 details -- constrained to real backend values, same as
  // ProfileSetupView.jsx, so a freshly-registered account can go straight
  // to the dashboard without a second round of "which district is this."
  const [location, setLocation] = useState('');
  const [landSize, setLandSize] = useState('');
  const [primaryCrop, setPrimaryCrop] = useState('');

  const [catalog, setCatalog] = useState(null);
  useEffect(() => {
    let cancelled = false;
    api.getCatalog()
      .then((data) => { if (!cancelled) setCatalog(data); })
      .catch(() => { if (!cancelled) setCatalog(null); });
    return () => { cancelled = true; };
  }, []);

  const cropOptions = useMemo(() => {
    if (!catalog?.crops_by_season) return FALLBACK_CROPS;
    const set = new Set();
    Object.values(catalog.crops_by_season).forEach((list) => list.forEach((c) => set.add(c)));
    return Array.from(set).sort();
  }, [catalog]);

  // OTP Verification details
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [timer, setTimer] = useState(45);
  const [resendDisabled, setResendDisabled] = useState(true);
  const otpInputsRef = useRef([]);

  const [toastVisible, setToastVisible] = useState(false);
  const [generatedOtp, setGeneratedOtp] = useState('');
  const [otpError, setOtpError] = useState('');

  const [loginError, setLoginError] = useState('');
  const [isLoginFlow, setIsLoginFlow] = useState(initialMode === 'login');

  useEffect(() => {
    let interval;
    let toastTimer;
    let hideTimer;
    if (subView === 'otp') {
      const code = Math.floor(100000 + Math.random() * 900000).toString();
      setGeneratedOtp(code);
      setOtpError('');
      setResendDisabled(true);
      setTimer(45);

      interval = setInterval(() => {
        setTimer((prev) => {
          if (prev <= 1) {
            clearInterval(interval);
            setResendDisabled(false);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      // Auto focus first OTP input
      setTimeout(() => {
        if (otpInputsRef.current[0]) {
          otpInputsRef.current[0].focus();
        }
      }, 100);

      // Show SMS Toast after 1 second
      toastTimer = setTimeout(() => {
        setToastVisible(true);
      }, 1000);

      // Hide SMS Toast after 10 seconds
      hideTimer = setTimeout(() => {
        setToastVisible(false);
      }, 11000);
    }
    return () => {
      clearInterval(interval);
      clearTimeout(toastTimer);
      clearTimeout(hideTimer);
    };
  }, [subView]);

  const handleOtpChange = (val, idx) => {
    if (isNaN(Number(val)) && val !== '') return;
    const newOtp = [...otp];
    newOtp[idx] = val.slice(-1);
    setOtp(newOtp);
    if (otpError) setOtpError('');

    // Auto-focus next input
    if (val !== '' && idx < 5) {
      otpInputsRef.current[idx + 1].focus();
    }
  };

  const handleOtpKeyDown = (e, idx) => {
    if (e.key === 'Backspace' && otp[idx] === '' && idx > 0) {
      otpInputsRef.current[idx - 1].focus();
    }
  };

  const handleResendCode = () => {
    setOtp(['', '', '', '', '', '']);
    setTimer(45);
    setResendDisabled(true);
    // Restart timer by triggering effect
    setSubView('login');
    setTimeout(() => setSubView('otp'), 50);
  };

  const autoFillOtp = () => {
    if (!generatedOtp) return;
    const digits = generatedOtp.split('');
    setOtp(digits);
    setOtpError('');
    setToastVisible(false);
    setTimeout(() => {
      if (otpInputsRef.current[5]) {
        otpInputsRef.current[5].focus();
      }
    }, 50);
  };

  const submitLogin = (e) => {
    e.preventDefault();

    // This app has no real backend auth -- credentials only ever live in
    // this browser's localStorage from a prior "Create Account" on this
    // device. If nothing was ever registered here, there is no account to
    // log into, so we say so rather than silently accepting any password.
    const registeredPassword = localStorage.getItem('agro_register_password');
    if (!registeredPassword) {
      setLoginError("No account found on this device yet. Please create an account first.");
      return;
    }
    if (password !== registeredPassword) {
      setLoginError('Incorrect password. Please try again.');
      return;
    }

    setLoginError('');
    // Simulate going to OTP
    setSubView('otp');
  };

  const submitRegister1 = (e) => {
    e.preventDefault();
    localStorage.setItem('agro_register_password', password);
    localStorage.setItem('agro_register_phone', phoneNumber);
    if (emailAddress) localStorage.setItem('agro_register_email', emailAddress);
    setSubView('register-2');
  };

  const submitRegister2 = (e) => {
    e.preventDefault();
    setSubView('otp');
  };

  const submitOtp = (e) => {
    if (e) e.preventDefault();
    const code = otp.join('');
    if (code.length < 6) return;

    if (generatedOtp && code !== generatedOtp) {
      setOtpError('Invalid verification code. Please try again.');
      return;
    }

    setOtpError('');

    // Only send fields this flow actually collected. A pure login (Login
    // tab -> OTP) never touches fullName/location/landSize/primaryCrop --
    // sending fake defaults for those used to silently overwrite a real
    // saved profile with "Jane Doe" / "Ahmedabad, Gujarat" on every login,
    // and let a genuinely new visitor skip straight past profile setup.
    // Omitting a key here means App.jsx's merge leaves whatever (if
    // anything) was already on file untouched.
    const payload = {};
    if (fullName) payload.fullName = fullName;
    if (phoneNumber) payload.phoneNumber = `${country.code} ${phoneNumber}`;
    if (emailAddress) payload.email = emailAddress;
    if (location) payload.location = location;
    if (landSize) payload.landSize = landSize;
    if (primaryCrop) payload.primaryCrop = primaryCrop;

    onSuccess(payload, isLoginFlow);
  };

  return (
    <div className="bg-background text-on-background min-h-screen flex flex-col font-body-md antialiased overflow-x-hidden relative">
      {/* Background Pattern */}
      <div
        className="fixed inset-0 pointer-events-none z-0 opacity-5"
        style={{
          backgroundImage: "radial-gradient(circle at 2px 2px, #005226 1px, transparent 0)",
          backgroundSize: '32px 32px'
        }}
      />

      {/* Main Content Area */}
      <main className="flex-grow flex items-center justify-center p-4 md:p-8 z-10 relative">
        <div className="w-full max-w-[480px]">
          {/* Logo Header */}
          <div className="text-center mb-8">
            <img
              alt="AgroOptimize Logo"
              className="h-20 mx-auto mb-4 object-contain"
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuAfHQj8K3STkpCK4V9BuRp9K-Xljc-I1IWfqZg3RJd4Pb83CRnmOrwzq5YvWYgSTr1Fr1t_86XS1mo3w4Yh2vM0noIiJe43zlDhONebdnRowgXVeT1ecDV4h_HX32wXazvfnQ5_-0uoZILfnfaRiaBRRkeJkNjlt3XLoatB_xHdJlxw16iz5rwNEwy52TFgYlE_YyE5_aTMONagpYeJ94v4G8GY2xdJVcbgDhEy6xEQs1mV_X7KmyVJ"
            />
          </div>

          {/* LOGIN VIEW */}
          {subView === 'login' && (
            <div className="flex flex-col gap-6 bg-surface-container-lowest rounded-xl p-6 md:p-8 shadow-ambient border border-outline-variant/20 animate-[fadeIn_0.3s_ease-out]">
              <div className="text-center">
                <h1 className="font-headline-lg-mobile md:font-headline-lg text-on-surface mb-2">Welcome Back</h1>
                <p className="text-on-surface-variant font-body-md">Sign in to manage your digital farm.</p>
              </div>

              {/* Tabs */}
              <div className="flex border-b border-outline-variant/30 mb-2">
                <button
                  onClick={() => { setLoginTab('phone'); if (loginError) setLoginError(''); }}
                  className={`flex-1 pb-3 text-center font-label-md transition-colors cursor-pointer ${
                    loginTab === 'phone'
                      ? 'border-b-2 border-primary text-primary font-bold'
                      : 'text-on-surface-variant border-b-2 border-transparent'
                  }`}
                >
                  Phone
                </button>
                <button
                  onClick={() => { setLoginTab('email'); if (loginError) setLoginError(''); }}
                  className={`flex-1 pb-3 text-center font-label-md transition-colors cursor-pointer ${
                    loginTab === 'email'
                      ? 'border-b-2 border-primary text-primary font-bold'
                      : 'text-on-surface-variant border-b-2 border-transparent'
                  }`}
                >
                  Email
                </button>
              </div>

              <form className="flex flex-col gap-5" onSubmit={submitLogin}>
                {/* Phone Input */}
                {loginTab === 'phone' && (
                  <div className="flex flex-col gap-1">
                    <label className="font-label-md text-on-surface">Phone Number</label>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setCountryModalOpen(true)}
                        className="w-24 min-h-[48px] rounded-lg border border-outline-variant bg-surface text-on-surface flex items-center justify-center gap-1 hover:bg-surface-container-low transition-colors"
                      >
                        <span className="text-xl">{country.flag}</span>
                        <span className="font-label-md">{country.code}</span>
                      </button>
                      <input
                        value={phoneNumber}
                        onChange={(e) => { setPhoneNumber(e.target.value); if (loginError) setLoginError(''); }}
                        className="flex-1 min-h-[48px] px-3 rounded-lg border border-outline-variant bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none"
                        placeholder="Enter phone number"
                        required
                        type="tel"
                      />
                    </div>
                  </div>
                )}

                {/* Email Input */}
                {loginTab === 'email' && (
                  <div className="flex flex-col gap-1">
                    <label className="font-label-md text-on-surface">Email Address</label>
                    <input
                      value={emailAddress}
                      onChange={(e) => { setEmailAddress(e.target.value); if (loginError) setLoginError(''); }}
                      className="w-full min-h-[48px] px-3 rounded-lg border border-outline-variant bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none"
                      placeholder="Enter your email"
                      required
                      type="email"
                    />
                  </div>
                )}

                {/* Password Input */}
                <div className="flex flex-col gap-1">
                  <label className="font-label-md text-on-surface">Password</label>
                  <div className="relative">
                    <input
                      value={password}
                      onChange={(e) => { setPassword(e.target.value); if (loginError) setLoginError(''); }}
                      className="w-full min-h-[48px] pl-3 pr-12 rounded-lg border border-outline-variant bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none"
                      placeholder="Enter password"
                      required
                      type={showPassword ? "text" : "password"}
                    />
                    <button
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-0 top-0 h-full w-12 flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
                      type="button"
                    >
                      <span className="material-symbols-outlined">
                        {showPassword ? "visibility_off" : "visibility"}
                      </span>
                    </button>
                  </div>
                  <div className="flex justify-end mt-1">
                    <a href="#" onClick={(e) => e.preventDefault()} className="text-primary font-label-sm hover:underline p-1">Forgot Password?</a>
                  </div>
                </div>

                {loginError && (
                  <div className="text-error font-label-sm text-center flex items-center justify-center gap-1.5 animate-[fadeIn_0.2s_ease-out] mb-1">
                    <span className="material-symbols-outlined text-[16px]">error</span>
                    {loginError}
                  </div>
                )}

                <button
                  type="submit"
                  className="w-full min-h-[48px] bg-primary text-on-primary font-label-md rounded-lg hover:opacity-90 transition-opacity shadow-sm flex items-center justify-center gap-2 mt-2 cursor-pointer"
                >
                  Log In
                </button>
              </form>

              <p className="text-center font-body-md text-on-surface-variant mt-2">
                Don't have an account?{' '}
                <button
                  onClick={() => { setSubView('register-1'); setIsLoginFlow(false); }}
                  className="text-primary font-label-md hover:underline p-1 cursor-pointer font-semibold"
                >
                  Create Account
                </button>
              </p>
            </div>
          )}

          {/* SIGNUP STEP 1 VIEW */}
          {subView === 'register-1' && (
            <div className="flex flex-col gap-6 bg-surface-container-lowest rounded-xl p-6 md:p-8 shadow-ambient border border-outline-variant/20 animate-[fadeIn_0.3s_ease-out]">
              <div className="flex items-center mb-2">
                <button
                  className="min-h-[48px] w-12 flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors -ml-3 cursor-pointer"
                  onClick={() => { setSubView('login'); setIsLoginFlow(true); }}
                >
                  <span className="material-symbols-outlined">arrow_back</span>
                </button>
                <div className="flex-1 text-center pr-9">
                  <h1 className="font-headline-lg-mobile md:font-headline-lg text-on-surface font-bold text-xl">Create Account</h1>
                </div>
              </div>

              <div className="flex justify-center gap-2 mb-4">
                <div className="w-8 h-2 rounded-full bg-primary"></div>
                <div className="w-8 h-2 rounded-full bg-surface-container-highest"></div>
              </div>

              <form className="flex flex-col gap-5" onSubmit={submitRegister1}>
                <div className="flex flex-col gap-1">
                  <label className="font-label-md text-on-surface">Full Name</label>
                  <input
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full min-h-[48px] px-3 rounded-lg border border-outline-variant bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none"
                    placeholder="Enter your full name"
                    required
                    type="text"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-label-md text-on-surface">Email Address (optional)</label>
                  <input
                    value={emailAddress}
                    onChange={(e) => setEmailAddress(e.target.value)}
                    className="w-full min-h-[48px] px-3 rounded-lg border border-outline-variant bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none"
                    placeholder="you@example.com"
                    type="email"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-label-md text-on-surface">Phone Number</label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setCountryModalOpen(true)}
                      className="w-24 min-h-[48px] rounded-lg border border-outline-variant bg-surface text-on-surface flex items-center justify-center gap-1 hover:bg-surface-container-low transition-colors"
                    >
                      <span className="text-xl">{country.flag}</span>
                      <span className="font-label-md">{country.code}</span>
                    </button>
                    <input
                      value={phoneNumber}
                      onChange={(e) => setPhoneNumber(e.target.value)}
                      className="flex-1 min-h-[48px] px-3 rounded-lg border border-outline-variant bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none"
                      placeholder="Enter phone number"
                      required
                      type="tel"
                    />
                  </div>
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-label-md text-on-surface">Create Password</label>
                  <div className="relative">
                    <input
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full min-h-[48px] pl-3 pr-12 rounded-lg border border-outline-variant bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none"
                      placeholder="At least 8 characters"
                      required
                      type={showPassword ? "text" : "password"}
                    />
                    <button
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-0 top-0 h-full w-12 flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors cursor-pointer"
                      type="button"
                    >
                      <span className="material-symbols-outlined">
                        {showPassword ? "visibility_off" : "visibility"}
                      </span>
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  className="w-full min-h-[48px] bg-primary text-on-primary font-label-md rounded-lg hover:opacity-90 transition-opacity shadow-sm flex items-center justify-center gap-2 mt-4 cursor-pointer"
                >
                  Continue
                  <span className="material-symbols-outlined text-[20px]">arrow_forward</span>
                </button>
              </form>
            </div>
          )}

          {/* SIGNUP STEP 2 VIEW (Farm Details) */}
          {subView === 'register-2' && (
            <div className="flex flex-col gap-6 bg-surface-container-lowest rounded-xl p-6 md:p-8 shadow-ambient border border-outline-variant/20 animate-[fadeIn_0.3s_ease-out]">
              <div className="flex items-center mb-2">
                <button
                  className="min-h-[48px] w-12 flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors -ml-3 cursor-pointer"
                  onClick={() => setSubView('register-1')}
                >
                  <span className="material-symbols-outlined">arrow_back</span>
                </button>
                <div className="flex-1 text-center pr-9">
                  <h1 className="font-headline-lg-mobile md:font-headline-lg text-on-surface font-bold text-xl">Farm Details</h1>
                </div>
              </div>

              <div className="flex justify-center gap-2 mb-4">
                <div className="w-8 h-2 rounded-full bg-primary"></div>
                <div className="w-8 h-2 rounded-full bg-primary"></div>
              </div>

              <p className="text-on-surface-variant font-body-md text-center mb-2">Help us customize your digital agronomist experience. This is required -- every dashboard, forecast, and report is generated for your specific district.</p>

              <form className="flex flex-col gap-5" onSubmit={submitRegister2}>
                <div className="flex flex-col gap-1">
                  <label className="font-label-md text-on-surface">Farm Location (District)</label>
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">location_on</span>
                    <select
                      value={location}
                      onChange={(e) => setLocation(e.target.value)}
                      className="w-full min-h-[48px] pl-10 pr-8 rounded-lg border border-outline-variant bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none appearance-none cursor-pointer"
                      required
                    >
                      <option value="" disabled>Select your district</option>
                      {DISTRICTS.map((d) => (
                        <option key={d} value={d}>{d}, Tamil Nadu</option>
                      ))}
                    </select>
                    <span className="material-symbols-outlined absolute right-2 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">expand_more</span>
                  </div>
                  <p className="font-label-sm text-label-sm text-on-surface-variant mt-1">Our models currently cover these {DISTRICTS.length} Tamil Nadu districts.</p>
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-label-md text-on-surface">Land Size (hectares)</label>
                  <input
                    value={landSize}
                    onChange={(e) => setLandSize(e.target.value)}
                    className="w-full min-h-[48px] px-3 rounded-lg border border-outline-variant bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none"
                    placeholder="e.g. 5"
                    required
                    type="number"
                    min="0.5"
                    step="0.5"
                  />
                </div>

                <div className="flex flex-col gap-1">
                  <label className="font-label-md text-on-surface">Primary Crop</label>
                  <select
                    value={primaryCrop}
                    onChange={(e) => setPrimaryCrop(e.target.value)}
                    className="w-full min-h-[48px] px-3 rounded-lg border border-outline-variant bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none cursor-pointer"
                    required
                  >
                    <option value="">Select main crop</option>
                    {cropOptions.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>

                <button
                  type="submit"
                  className="w-full min-h-[48px] bg-primary text-on-primary font-label-md rounded-lg hover:opacity-90 transition-opacity shadow-sm flex items-center justify-center gap-2 mt-4 cursor-pointer"
                >
                  Complete Setup
                  <span className="material-symbols-outlined text-[20px]">check</span>
                </button>
              </form>
            </div>
          )}

          {/* OTP VERIFICATION VIEW */}
          {subView === 'otp' && (
            <div className="flex flex-col gap-6 bg-surface-container-lowest rounded-xl p-6 md:p-8 items-center shadow-ambient border border-outline-variant/20 animate-[fadeIn_0.3s_ease-out]">
              <div className="w-full flex justify-start mb-2">
                <button
                  className="min-h-[48px] w-12 flex items-center justify-center text-on-surface-variant hover:text-primary transition-colors -ml-3 cursor-pointer"
                  onClick={() => setSubView('login')}
                >
                  <span className="material-symbols-outlined">arrow_back</span>
                </button>
              </div>

              <div className="w-16 h-16 bg-primary-container/10 rounded-full flex items-center justify-center text-primary mb-2">
                <span className="material-symbols-outlined text-[32px]">dialpad</span>
              </div>

              <div className="text-center w-full">
                <h1 className="font-headline-lg-mobile md:font-headline-lg text-on-surface mb-2">Enter Code</h1>
                <p className="text-on-surface-variant font-body-md">We sent a 6-digit code to your phone.</p>
              </div>

              <div className="flex gap-2 justify-center w-full my-4">
                {otp.map((val, idx) => (
                  <input
                    key={idx}
                    ref={(el) => (otpInputsRef.current[idx] = el)}
                    value={val}
                    onChange={(e) => handleOtpChange(e.target.value, idx)}
                    onKeyDown={(e) => handleOtpKeyDown(e, idx)}
                    className="w-12 h-14 text-center text-2xl font-bold border border-outline-variant rounded-lg bg-surface text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none focus:shadow-sm"
                    maxLength={1}
                    type="text"
                    pattern="[0-9]*"
                    inputMode="numeric"
                  />
                ))}
              </div>

              {otpError && (
                <div className="text-error font-label-sm text-center mb-3 flex items-center justify-center gap-1.5 animate-[fadeIn_0.2s_ease-out]">
                  <span className="material-symbols-outlined text-[16px]">error</span>
                  {otpError}
                </div>
              )}

              <button
                onClick={() => submitOtp()}
                disabled={otp.join('').length < 6}
                className="w-full min-h-[48px] bg-primary text-on-primary font-label-md rounded-lg hover:opacity-90 transition-opacity shadow-sm flex items-center justify-center mt-2 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                Verify &amp; Proceed
              </button>

              <div className="text-center mt-4 flex flex-col gap-2">
                <p className="font-label-md text-on-surface-variant font-semibold">
                  00:{timer < 10 ? `0${timer}` : timer}
                </p>
                <button
                  onClick={handleResendCode}
                  disabled={resendDisabled}
                  className="text-primary font-label-md hover:underline p-2 disabled:text-outline-variant disabled:hover:no-underline cursor-pointer"
                >
                  Resend Code
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Country Selection Modal */}
      <CountryCodeModal
        isOpen={countryModalOpen}
        onClose={() => setCountryModalOpen(false)}
        selectedCode={country.code}
        onSelect={(c) => setCountry(c)}
      />

      {/* SMS OTP Toast Notification */}
      {subView === 'otp' && toastVisible && (
        <div className="slide-down-toast z-50 w-[90%] max-w-[400px] bg-inverse-surface/95 text-inverse-on-surface backdrop-blur-md rounded-xl p-4 shadow-2xl border border-white/10 flex gap-3.5 items-start">
          <div className="bg-primary/20 text-primary-fixed p-2 rounded-lg flex items-center justify-center">
            <span className="material-symbols-outlined text-primary-fixed">sms</span>
          </div>
          <div className="flex-grow">
            <div className="flex justify-between items-center mb-0.5">
              <span className="font-label-md font-bold text-inverse-on-surface">Messages</span>
              <span className="font-label-sm text-white/50 text-[11px]">now</span>
            </div>
            <p className="font-body-md text-sm text-white/95 mb-3 leading-relaxed">
              Your AgroOptimize code is <strong className="text-primary-fixed-dim font-mono text-base tracking-wider bg-black/20 px-1.5 py-0.5 rounded">{generatedOtp}</strong>. It will expire in 10 minutes.
            </p>
            <div className="flex gap-2">
              <button
                onClick={autoFillOtp}
                className="bg-primary hover:bg-primary/90 text-on-primary px-3 py-1.5 rounded-lg text-xs font-bold cursor-pointer transition-colors shadow-sm flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-xs">done</span>
                Auto-fill Code
              </button>
              <button
                onClick={() => setToastVisible(false)}
                className="bg-white/10 hover:bg-white/20 text-white px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer transition-colors"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
