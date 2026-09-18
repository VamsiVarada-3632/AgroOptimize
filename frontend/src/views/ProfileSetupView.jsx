import React, { useState, useRef, useEffect, useMemo } from 'react';
import SuccessCheckSvg from '../components/SuccessCheckSvg';
import { api, DISTRICTS } from '../services/api';

// Generic fallback profile SVG
const defaultAvatar = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23707a6f'><path d='M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z'/></svg>";

// Small fallback crop list, used only if GET /api/catalog is unreachable --
// same list SettingsView.jsx falls back to, so the two stay consistent.
const FALLBACK_CROPS = ['Sugarcane', 'Wheat', 'Paddy', 'Maize', 'Cotton', 'Groundnut', 'Sorghum', 'Tapioca'];

// The backend only models these three real growing seasons (see
// GET /api/catalog -> seasons). No generic spring/summer/fall/winter here.
const SEASONS = ['Kharif', 'Rabi', 'Summer'];

export default function ProfileSetupView({ onComplete, initialProfile }) {
  const [step, setStep] = useState(1); // 1: Personal Details / Photo, 2: Farm Details, 3: Verification Success
  const fileInputRef = useRef(null);

  // Step 1 States
  const [firstName, setFirstName] = useState(initialProfile?.fullName?.split(' ')[0] || '');
  const [lastName, setLastName] = useState(initialProfile?.fullName?.split(' ')[1] || '');
  const [avatar, setAvatar] = useState(initialProfile?.avatar || null);

  // Step 2 States -- location & crop are constrained to real backend values
  // (a farmer picks from what the models actually cover, nothing free-text
  // that we'd have to silently coerce or fake later).
  const [location, setLocation] = useState(
    DISTRICTS.includes(initialProfile?.location) ? initialProfile.location : ''
  );
  const [season, setSeason] = useState(
    SEASONS.includes(initialProfile?.season) ? initialProfile.season : 'Kharif'
  );
  const [crop, setCrop] = useState(initialProfile?.primaryCrop || '');
  // Hectares, matching the backend's total_land_ha field -- this used to be
  // mislabeled "acres" while feeding total_land_ha directly, a real ~2.47x
  // unit error. Now the label, unit, and stored value all agree.
  const [landSizeHa, setLandSizeHa] = useState(initialProfile?.landSize || '');

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

  const handlePhotoClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (uploadEvent) => {
        setAvatar(uploadEvent.target.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleStep1Submit = (e) => {
    e.preventDefault();
    setStep(2);
  };

  const handleStep2Submit = (e) => {
    e.preventDefault();
    setStep(3);
  };

  const handleCompleteFlow = () => {
    // No fake defaults -- location, season, crop, and land size are all
    // required fields on the step-2 form (which can no longer be skipped),
    // so by the time we get here they're genuinely what the user entered.
    // Full name/avatar stay optional since step 1 can still be skipped.
    onComplete({
      fullName: `${firstName} ${lastName}`.trim(),
      location,
      landSize: landSizeHa,
      primaryCrop: crop,
      avatar: avatar,
      season: season
    });
  };

  return (
    <div className="bg-background min-h-screen flex flex-col font-body-md antialiased text-on-surface relative">
      {/* Ambient background element for warmth */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute -top-[20%] -left-[10%] w-[70%] h-[70%] rounded-full bg-primary-fixed/20 blur-3xl opacity-50 mix-blend-multiply"></div>
        <div className="absolute top-[40%] -right-[20%] w-[60%] h-[80%] rounded-full bg-secondary-fixed/20 blur-3xl opacity-50 mix-blend-multiply"></div>
      </div>

      {/* Header (Transactional flow style) */}
      {step < 3 && (
        <header className="bg-surface w-full z-40 h-16 flex justify-between items-center px-4 md:px-8 border-b border-surface-variant relative">
          <div className="font-headline-md text-headline-md font-bold text-primary flex items-center gap-2">
            <span className="material-symbols-outlined" style={{ fontVariationSettings: "'FILL' 1" }}>spa</span>
            AgroOptimize
          </div>
          <div>
            <span className="font-label-md text-label-md text-on-surface-variant">Step {step} of 2</span>
          </div>
        </header>
      )}

      {/* View Contents */}
      <main className="flex-grow flex items-center justify-center p-4 md:p-8 z-10 relative">
        {step === 1 && (
          <div className="w-full max-w-md bg-surface-container-lowest rounded-xl shadow-[0_4px_16px_rgba(31,107,58,0.08)] p-8 border border-outline-variant/30 flex flex-col items-center animate-[fadeIn_0.3s_ease-out]">
            {/* Logo */}
            <div className="mb-6 w-32 h-auto flex justify-center">
              <img
                alt="AgroOptimize Logo"
                className="w-full h-auto object-contain"
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuAfHQj8K3STkpCK4V9BuRp9K-Xljc-I1IWfqZg3RJd4Pb83CRnmOrwzq5YvWYgSTr1Fr1t_86XS1mo3w4Yh2vM0noIiJe43zlDhONebdnRowgXVeT1ecDV4h_HX32wXazvfnQ5_-0uoZILfnfaRiaBRRkeJkNjlt3XLoatB_xHdJlxw16iz5rwNEwy52TFgYlE_YyE5_aTMONagpYeJ94v4G8GY2xdJVcbgDhEy6xEQs1mV_X7KmyVJ"
              />
            </div>

            <h1 className="font-headline-lg-mobile text-headline-lg-mobile text-on-surface mb-2 text-center md:font-headline-lg md:text-headline-lg">
              Welcome!
            </h1>
            <p className="font-body-md text-body-md text-on-surface-variant text-center mb-6">
              Let's get to know you.
            </p>

            <form className="w-full flex flex-col gap-5" onSubmit={handleStep1Submit}>
              {/* Profile Picture Setup */}
              <div className="flex flex-col items-center gap-3">
                <input
                  type="file"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  accept="image/*"
                  style={{ display: 'none' }}
                />

                <div
                  onClick={handlePhotoClick}
                  className="relative group w-24 h-24 rounded-full bg-surface-container flex items-center justify-center border-2 border-dashed border-outline-variant hover:border-primary overflow-hidden cursor-pointer"
                >
                  <img src={avatar || defaultAvatar} alt="Avatar" className="w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-on-surface/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center pointer-events-none">
                    <span className="material-symbols-outlined text-white text-2xl">upload</span>
                  </div>
                </div>

                <div className="flex gap-4 mt-1">
                  <button
                    type="button"
                    onClick={handlePhotoClick}
                    className="flex items-center gap-1 text-label-sm text-primary hover:underline cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-sm">upload</span>
                    Upload Photo
                  </button>
                  <button
                    type="button"
                    onClick={() => setAvatar(null)}
                    className="flex items-center gap-1 text-label-sm text-primary hover:underline cursor-pointer"
                  >
                    <span className="material-symbols-outlined text-sm">restart_alt</span>
                    Reset
                  </button>
                </div>
              </div>

              {/* Personal Details */}
              <div className="flex flex-col gap-4 w-full mt-2">
                <div className="flex flex-col gap-1 w-full">
                  <label className="font-label-md text-label-md text-on-surface">First Name</label>
                  <input
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    className="w-full h-12 px-4 rounded-lg bg-surface-container-lowest border border-outline-variant text-on-surface font-body-md text-body-md focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-shadow"
                    placeholder="e.g. Ravi"
                    required
                    type="text"
                  />
                </div>
                <div className="flex flex-col gap-1 w-full">
                  <label className="font-label-md text-label-md text-on-surface">Last Name</label>
                  <input
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    className="w-full h-12 px-4 rounded-lg bg-surface-container-lowest border border-outline-variant text-on-surface font-body-md text-body-md focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-shadow"
                    placeholder="e.g. Kumar"
                    required
                    type="text"
                  />
                </div>
              </div>

              <div className="mt-4 w-full flex flex-col items-center">
                <button
                  type="submit"
                  className="w-full h-12 bg-primary text-on-primary font-label-md text-label-md rounded-lg hover:opacity-90 active:scale-[0.98] transition-all flex items-center justify-center shadow-sm cursor-pointer font-semibold"
                >
                  Continue
                </button>
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="mt-4 font-label-md text-label-md text-primary hover:text-primary-container transition-colors p-2 cursor-pointer"
                >
                  Skip for now
                </button>
              </div>
            </form>
          </div>
        )}

        {step === 2 && (
          <div className="w-full max-w-2xl bg-surface-container-lowest rounded-xl shadow-[0_4px_16px_rgba(31,107,58,0.08)] p-6 md:p-8 border border-outline-variant/30 animate-[fadeIn_0.3s_ease-out]">
            <div className="mb-6 text-center">
              <h1 className="font-headline-lg-mobile md:font-headline-lg text-headline-lg-mobile md:text-headline-lg text-primary mb-2">Complete Your Farm Profile</h1>
              <p className="font-body-lg text-body-lg text-on-surface-variant">Tell us a bit about your operation to tailor our fuzzy logic models for your specific environment. This is required -- every dashboard, forecast, and report is generated for your specific district.</p>
            </div>

            <form className="space-y-6" onSubmit={handleStep2Submit}>
              {/* Location */}
              <div>
                <label className="block font-label-md text-label-md text-on-surface mb-2">Farm Location (District)</label>
                <div className="relative">
                  <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">location_on</span>
                  <select
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    className="w-full min-h-[48px] pl-12 pr-10 py-3 bg-surface-bright border border-outline-variant rounded-lg font-body-md text-body-md text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-colors appearance-none cursor-pointer"
                    required
                  >
                    <option value="" disabled>Select your district</option>
                    {DISTRICTS.map((d) => (
                      <option key={d} value={d}>{d}, Tamil Nadu</option>
                    ))}
                  </select>
                  <span className="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">expand_more</span>
                </div>
                <p className="font-label-sm text-label-sm text-on-surface-variant mt-1">Our models currently cover these {DISTRICTS.length} Tamil Nadu districts.</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Growing Season */}
                <div>
                  <label className="block font-label-md text-label-md text-on-surface mb-2">Current Growing Season</label>
                  <div className="relative">
                    <select
                      value={season}
                      onChange={(e) => setSeason(e.target.value)}
                      className="w-full min-h-[48px] pl-4 pr-10 py-3 bg-surface-bright border border-outline-variant rounded-lg font-body-md text-body-md text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-colors appearance-none cursor-pointer"
                    >
                      {SEASONS.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                    <span className="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">expand_more</span>
                  </div>
                </div>

                {/* Crop Field */}
                <div>
                  <label className="block font-label-md text-label-md text-on-surface mb-2">Primary Crop Type</label>
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">grass</span>
                    <select
                      value={crop}
                      onChange={(e) => setCrop(e.target.value)}
                      className="w-full min-h-[48px] pl-12 pr-10 py-3 bg-surface-bright border border-outline-variant rounded-lg font-body-md text-body-md text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-colors appearance-none cursor-pointer"
                      required
                    >
                      <option value="" disabled>Select main crop</option>
                      {cropOptions.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                    <span className="material-symbols-outlined absolute right-4 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">expand_more</span>
                  </div>
                </div>
              </div>

              {/* Land size */}
              <div>
                <label className="block font-label-md text-label-md text-on-surface mb-2">Total Land Size</label>
                <div className="relative">
                  <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">landscape</span>
                  <input
                    value={landSizeHa}
                    onChange={(e) => setLandSizeHa(e.target.value)}
                    className="w-full min-h-[48px] pl-12 pr-24 py-3 bg-surface-bright border border-outline-variant rounded-lg font-body-md text-body-md text-on-surface focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-colors"
                    placeholder="e.g. 5"
                    required
                    type="number"
                    min="0.5"
                    step="0.5"
                  />
                  <div className="absolute inset-y-0 right-0 flex items-center pr-4 pointer-events-none">
                    <span className="font-body-md text-body-md text-on-surface-variant">hectares</span>
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="pt-6 flex justify-end">
                <button
                  type="submit"
                  className="w-full md:w-auto min-h-[48px] px-8 py-3 bg-primary text-on-primary font-label-md text-label-md rounded-lg hover:bg-surface-tint active:scale-95 transition-all shadow-sm flex items-center justify-center cursor-pointer font-semibold"
                >
                  Continue to Verification
                </button>
              </div>
            </form>
          </div>
        )}

        {step === 3 && (
          <div className="max-w-md w-full flex flex-col items-center text-center space-y-6 animate-[fadeIn_0.5s_ease-out]">
            <img
              alt="AgroOptimize Logo"
              className="h-16 w-auto mb-2 object-contain"
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuAfHQj8K3STkpCK4V9BuRp9K-Xljc-I1IWfqZg3RJd4Pb83CRnmOrwzq5YvWYgSTr1Fr1t_86XS1mo3w4Yh2vM0noIiJe43zlDhONebdnRowgXVeT1ecDV4h_HX32wXazvfnQ5_-0uoZILfnfaRiaBRRkeJkNjlt3XLoatB_xHdJlxw16iz5rwNEwy52TFgYlE_YyE5_aTMONagpYeJ94v4G8GY2xdJVcbgDhEy6xEQs1mV_X7KmyVJ"
            />

            <div className="relative w-32 h-32 flex items-center justify-center">
              <SuccessCheckSvg />
            </div>

            <div className="space-y-2 w-full">
              <h1 className="font-headline-lg-mobile md:font-headline-lg text-primary font-bold">Verification completed</h1>
              <p className="text-on-surface-variant max-w-sm mx-auto">Your account has been successfully verified. You are now ready to start optimizing your yields.</p>
            </div>

            <div className="pt-2 w-full">
              <button
                onClick={handleCompleteFlow}
                className="w-full sm:w-auto min-h-[48px] bg-primary text-on-primary font-label-md px-8 py-3 rounded-full hover:bg-primary/95 transition-colors focus:outline-none focus:ring-2 focus:ring-primary cursor-pointer font-semibold"
              >
                Continue to Dashboard
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
