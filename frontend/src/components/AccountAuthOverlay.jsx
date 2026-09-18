import React from 'react';

export default function AccountAuthOverlay({ isOpen, onClose, onConfirm }) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-inverse-surface/40 backdrop-blur-sm p-4 animate-[fadeIn_0.2s_ease-out]">
      <div className="bg-surface-container-lowest w-full max-w-md rounded-xl shadow-ambient p-8 flex flex-col items-center">
        {/* Logo Header */}
        <div className="mb-6 flex flex-col items-center">
          <img 
            alt="AgroOptimize Logo" 
            className="w-32 h-auto mb-4 object-contain" 
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuAfHQj8K3STkpCK4V9BuRp9K-Xljc-I1IWfqZg3RJd4Pb83CRnmOrwzq5YvWYgSTr1Fr1t_86XS1mo3w4Yh2vM0noIiJe43zlDhONebdnRowgXVeT1ecDV4h_HX32wXazvfnQ5_-0uoZILfnfaRiaBRRkeJkNjlt3XLoatB_xHdJlxw16iz5rwNEwy52TFgYlE_YyE5_aTMONagpYeJ94v4G8GY2xdJVcbgDhEy6xEQs1mV_X7KmyVJ"
          />
          <h1 className="font-headline-md text-headline-md text-on-surface text-center">Authorization Required</h1>
        </div>

        {/* Request Details */}
        <div className="w-full mb-8 text-center">
          <p className="font-body-md text-body-md text-on-surface-variant mb-4">
            <strong>AgroOptimize</strong> is requesting access to your basic profile information.
          </p>
          <div className="bg-surface-container-low rounded-lg p-4 text-left border border-outline-variant">
            <p className="font-label-md text-label-md text-on-surface mb-2">This will allow the application to access:</p>
            <ul className="space-y-3">
              <li className="flex items-start">
                <span 
                  className="material-symbols-outlined text-primary mr-2" 
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  check_circle
                </span>
                <span className="font-body-md text-body-md text-on-surface-variant">Name and profile picture</span>
              </li>
              <li className="flex items-start">
                <span 
                  className="material-symbols-outlined text-primary mr-2" 
                  style={{ fontVariationSettings: "'FILL' 1" }}
                >
                  check_circle
                </span>
                <span className="font-body-md text-body-md text-on-surface-variant">Email address</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Actions */}
        <div className="flex w-full gap-4">
          <button 
            onClick={onClose}
            className="flex-1 h-12 border-[1.5px] border-primary-container text-primary-container font-label-md text-label-md rounded-lg hover:bg-surface-container-low transition-colors duration-200 flex items-center justify-center cursor-pointer" 
            type="button"
          >
            Cancel
          </button>
          <button 
            onClick={onConfirm}
            className="flex-1 h-12 bg-primary text-on-primary font-label-md text-label-md rounded-lg hover:opacity-90 transition-opacity duration-200 flex items-center justify-center shadow-sm cursor-pointer" 
            type="button"
          >
            Confirm
          </button>
        </div>

        <div className="mt-6 text-center">
          <p className="font-label-sm text-label-sm text-outline">
            By confirming, you agree to our <a className="text-primary hover:underline" href="#">Terms of Service</a> and <a className="text-primary hover:underline" href="#">Privacy Policy</a>.
          </p>
        </div>
      </div>
    </div>
  );
}
