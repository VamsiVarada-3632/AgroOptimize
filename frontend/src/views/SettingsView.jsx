import React, { useState, useRef, useEffect, useMemo } from 'react';
import AccountAuthOverlay from '../components/AccountAuthOverlay';
import { api, DISTRICTS, extractDistrict } from '../services/api';

const defaultAvatar = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23707a6f'><path d='M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z'/></svg>";

// Small fallback crop list, used only if GET /api/catalog is unreachable.
const FALLBACK_CROPS = ['Sugarcane', 'Wheat', 'Paddy', 'Maize', 'Cotton', 'Groundnut', 'Sorghum', 'Tapioca'];

export default function SettingsView({ user, onUpdateUser, onLogout, onChangeLanguage, selectedLanguage }) {
  const fileInputRef = useRef(null);
  const [fullName, setFullName] = useState(user.fullName || '');
  const [email, setEmail] = useState(user.email || '');
  const [phone, setPhone] = useState(user.phoneNumber || '');

  // Farm profile fields -- location is constrained to a dropdown of the 4
  // districts the backend actually has data for (any pre-existing
  // free-text location is resolved onto one of them via extractDistrict).
  const [location, setLocation] = useState(extractDistrict(user.location));
  const [landSize, setLandSize] = useState(user.landSize || '5');
  const [primaryCrop, setPrimaryCrop] = useState(user.primaryCrop || '');

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
        onUpdateUser({ avatar: uploadEvent.target.result });
      };
      reader.readAsDataURL(file);
    }
  };

  // Reminders toggles
  const [irrigationReminders, setIrrigationReminders] = useState(true);
  const [weatherWarnings, setWeatherWarnings] = useState(true);

  // Auth Overlay state
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [isGoogleLinked, setIsGoogleLinked] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    onUpdateUser({
      fullName,
      email,
      phoneNumber: phone,
      location,
      landSize,
      primaryCrop,
    });
    alert("Profile changes saved successfully!");
  };

  const handleUnlinkGoogle = () => {
    setIsAuthOpen(true);
  };

  const handleConfirmUnlink = () => {
    setIsGoogleLinked(false);
    setIsAuthOpen(false);
    alert("Google account unlinked successfully.");
  };

  return (
    <div className="animate-[fadeIn_0.2s_ease-out] w-full">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-start">
        {/* Profile Section */}
        <section className="md:col-span-2 bg-surface-container-lowest rounded-xl p-6 shadow-soft border border-outline-variant/20">
          <h3 className="font-headline-md text-headline-md text-on-surface mb-6 flex items-center gap-2 font-bold">
            <span className="material-symbols-outlined text-primary">person</span>
            Profile Details
          </h3>
          
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="flex flex-col sm:flex-row gap-6 mb-6">
              <div className="flex flex-col items-center gap-4">
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  onChange={handleFileChange} 
                  accept="image/*" 
                  style={{ display: 'none' }} 
                />
                <div 
                  onClick={handlePhotoClick}
                  className="w-24 h-24 rounded-full overflow-hidden border-4 border-surface-container bg-surface-variant flex-shrink-0 cursor-pointer hover:border-primary transition-colors"
                >
                  <img 
                    alt="Profile Photo" 
                    className="w-full h-full object-cover" 
                    src={user.avatar || defaultAvatar}
                  />
                </div>
                <button 
                  type="button" 
                  onClick={handlePhotoClick} 
                  className="font-label-sm text-label-sm text-primary hover:text-primary-container font-semibold cursor-pointer"
                >
                  Change Photo
                </button>
              </div>

              <div className="flex-grow space-y-4">
                <div>
                  <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Full Name</label>
                  <input 
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright focus:border-primary focus:ring-1 focus:ring-primary text-on-surface font-body-md outline-none transition-colors" 
                    type="text" 
                  />
                </div>
                <div>
                  <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Email Address</label>
                  <input 
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright focus:border-primary focus:ring-1 focus:ring-primary text-on-surface font-body-md outline-none transition-colors" 
                    type="email" 
                  />
                </div>
                <div>
                  <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Phone Number</label>
                  <input
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright focus:border-primary focus:ring-1 focus:ring-primary text-on-surface font-body-md outline-none transition-colors"
                    type="tel"
                  />
                </div>
              </div>
            </div>

            {/* Farm profile: district, land size, primary crop -- feeds
                every other view's district-scoped API calls via
                extractDistrict(user.location). */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
              <div>
                <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Farm Location</label>
                <select
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright focus:border-primary focus:ring-1 focus:ring-primary text-on-surface font-body-md outline-none transition-colors cursor-pointer"
                >
                  {DISTRICTS.map((d) => (
                    <option key={d} value={d}>{d}, Tamil Nadu</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Land Size (hectares)</label>
                <input
                  value={landSize}
                  onChange={(e) => setLandSize(e.target.value)}
                  className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright focus:border-primary focus:ring-1 focus:ring-primary text-on-surface font-body-md outline-none transition-colors"
                  type="number"
                  min="0.5"
                  step="0.5"
                />
              </div>
              <div>
                <label className="block font-label-sm text-label-sm text-on-surface-variant mb-1 font-semibold">Primary Crop</label>
                <select
                  value={primaryCrop}
                  onChange={(e) => setPrimaryCrop(e.target.value)}
                  className="w-full h-12 px-4 rounded-lg border border-outline-variant bg-surface-bright focus:border-primary focus:ring-1 focus:ring-primary text-on-surface font-body-md outline-none transition-colors cursor-pointer"
                >
                  <option value="">Select a crop</option>
                  {cropOptions.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex justify-end pt-4 border-t border-outline-variant/20">
              <button 
                type="submit" 
                className="h-12 px-6 bg-primary text-on-primary rounded-lg font-label-md text-label-md hover:opacity-95 transition-opacity shadow-sm cursor-pointer font-bold"
              >
                Save Changes
              </button>
            </div>
          </form>
        </section>

        {/* Sidebar Preferences */}
        <div className="space-y-6 w-full">
          {/* Language preference */}
          <section className="bg-surface-container-lowest rounded-xl p-6 shadow-soft border border-outline-variant/20 w-full">
            <h3 className="font-headline-md text-headline-md text-on-surface mb-4 flex items-center gap-2 font-bold">
              <span className="material-symbols-outlined text-primary">language</span>
              Language
            </h3>
            
            <div className="space-y-3">
              {[
                { id: 'en', label: 'English' },
                { id: 'hi', label: 'Hindi (हिंदी)' },
                { id: 'ta', label: 'Tamil (தமிழ்)' }
              ].map((lang) => {
                const isActive = selectedLanguage === lang.id;
                return (
                  <label 
                    key={lang.id}
                    onClick={() => onChangeLanguage(lang.id)}
                    className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer h-12 transition-all ${
                      isActive 
                        ? 'border-primary bg-primary/5 font-bold text-primary' 
                        : 'border-outline-variant hover:border-primary/50 text-on-surface'
                    }`}
                  >
                    <span className="font-body-md text-body-md">{lang.label}</span>
                    <input 
                      readOnly
                      checked={isActive}
                      className="text-primary focus:ring-primary w-5 h-5 cursor-pointer accent-primary" 
                      name="lang" 
                      type="radio"
                    />
                  </label>
                );
              })}
            </div>
          </section>

          {/* Quick Logout Button for mobile */}
          <div className="w-full">
            <button 
              onClick={onLogout}
              className="w-full h-12 border-2 border-error text-error rounded-lg font-label-md text-label-md hover:bg-error/5 transition-colors flex items-center justify-center gap-2 cursor-pointer font-bold"
            >
              <span className="material-symbols-outlined">logout</span>
              Log Out
            </button>
          </div>
        </div>
      </div>

      {/* Notifications & Security */}
      <section className="bg-surface-container-lowest rounded-xl p-6 shadow-soft border border-outline-variant/20 mt-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {/* Notifications */}
          <div>
            <h3 className="font-headline-md text-headline-md text-on-surface mb-4 flex items-center gap-2 font-bold">
              <span className="material-symbols-outlined text-primary">notifications_active</span>
              Notifications
            </h3>
            
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-body-md text-body-md text-on-surface font-semibold">Irrigation Reminders</p>
                  <p className="font-label-sm text-label-sm text-on-surface-variant">Alerts based on moisture sensors</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input 
                    checked={irrigationReminders}
                    onChange={(e) => setIrrigationReminders(e.target.checked)}
                    className="sr-only peer" 
                    type="checkbox" 
                  />
                  <div className="w-11 h-6 bg-surface-variant peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                </label>
              </div>
              
              <div className="flex items-center justify-between pt-2">
                <div>
                  <p className="font-body-md text-body-md text-on-surface font-semibold">Weather Warnings</p>
                  <p className="font-label-sm text-label-sm text-on-surface-variant">Frost, heavy rain, or extreme heat</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input 
                    checked={weatherWarnings}
                    onChange={(e) => setWeatherWarnings(e.target.checked)}
                    className="sr-only peer" 
                    type="checkbox" 
                  />
                  <div className="w-11 h-6 bg-surface-variant peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                </label>
              </div>
            </div>
          </div>

          {/* Security details */}
          <div>
            <h3 className="font-headline-md text-headline-md text-on-surface mb-4 flex items-center gap-2 font-bold">
              <span className="material-symbols-outlined text-primary">security</span>
              Security
            </h3>
            
            <div className="bg-surface-container p-4 rounded-lg border border-outline-variant/30">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-3">
                  <div className="bg-white p-1 rounded">
                    <svg className="w-5 h-5" viewBox="0 0 24 24">
                      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"></path>
                      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"></path>
                      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"></path>
                      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"></path>
                    </svg>
                  </div>
                  <span className="font-body-md text-body-md text-on-surface font-semibold">Google Account</span>
                </div>
                <span className={`font-label-sm text-label-sm px-2.5 py-1 rounded font-bold ${
                  isGoogleLinked ? 'bg-primary-container text-on-primary' : 'bg-surface-variant text-on-surface-variant'
                }`}>
                  {isGoogleLinked ? 'Linked' : 'Not Linked'}
                </span>
              </div>
              <p className="font-label-sm text-label-sm text-on-surface-variant mb-4">{email}</p>
              
              {isGoogleLinked ? (
                <button 
                  onClick={handleUnlinkGoogle}
                  className="font-label-md text-label-md text-primary font-semibold hover:underline cursor-pointer"
                >
                  Unlink Account
                </button>
              ) : (
                <button 
                  onClick={() => { setIsGoogleLinked(true); alert("Google account linked successfully!"); }}
                  className="font-label-md text-label-md text-primary font-semibold hover:underline cursor-pointer"
                >
                  Link Google Account
                </button>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Account Authorization Overlay Modal */}
      <AccountAuthOverlay 
        isOpen={isAuthOpen}
        onClose={() => setIsAuthOpen(false)}
        onConfirm={handleConfirmUnlink}
      />
    </div>
  );
}
