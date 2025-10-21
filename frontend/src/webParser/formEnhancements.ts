/**
 * Form-specific enhancements for demo/training purposes.
 * 
 * This module provides option lists and constraints for forms where
 * JavaScript-rendered controls don't expose their options in the DOM.
 */

export interface FormEnhancementConfig {
  /** URL pattern to match (can be partial match) */
  urlPattern: string;
  
  /** Field-specific option overrides */
  fieldOptions?: Record<string, string[]>;
  
  /** Field-specific constraint overrides */
  fieldConstraints?: Record<string, Record<string, string | number | boolean>>;
}

// Common option lists that can be reused across forms
export const COMMON_OPTIONS = {
  YES_NO: ['Yes', 'No'],
  
  US_STATES: [
    'Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado',
    'Connecticut', 'Delaware', 'Florida', 'Georgia', 'Hawaii', 'Idaho',
    'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana',
    'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'Minnesota',
    'Mississippi', 'Missouri', 'Montana', 'Nebraska', 'Nevada',
    'New Hampshire', 'New Jersey', 'New Mexico', 'New York',
    'North Carolina', 'North Dakota', 'Ohio', 'Oklahoma', 'Oregon',
    'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota',
    'Tennessee', 'Texas', 'Utah', 'Vermont', 'Virginia', 'Washington',
    'West Virginia', 'Wisconsin', 'Wyoming'
  ],
  
  SCHOOL_TYPES: [
    'Unspecified',
    'High School',
    'Community College',
    'Vocational College',
    'College / University',
    'Graduate School',
    'Specialized',
    'Other'
  ],
  
  // Simplified country list (top countries by usage)
  COUNTRIES: [
    'United States',
    'Canada',
    'Mexico',
    'United Kingdom',
    'Australia',
    'Germany',
    'France',
    'India',
    'China',
    'Japan',
    'Brazil',
    'Spain',
    'Italy',
    'Netherlands',
    'Sweden',
    'Other'
  ]
};

/**
 * Form-specific configurations for demo/training forms
 */
export const FORM_ENHANCEMENTS: FormEnhancementConfig[] = [
  {
    // Cowlitz Family Health Center - Nurse Practitioner Application (Paylocity)
    urlPattern: 'recruiting.paylocity.com/Recruiting/Jobs/Apply/3612061',
    
    fieldOptions: {
      // Information section
      'info.haveYouAppliedWithUsBefore': COMMON_OPTIONS.YES_NO,
      'info.smsOptedIn': COMMON_OPTIONS.YES_NO,
      'info.haveYouWorkedWithUsBefore': COMMON_OPTIONS.YES_NO,
      
      // Address fields (main)
      'public-site-address-country': COMMON_OPTIONS.COUNTRIES,
      'public-site-address-us-state': COMMON_OPTIONS.US_STATES,
      
      // Work History address fields
      'public-candidate-work-history-address-0-country': COMMON_OPTIONS.COUNTRIES,
      'public-candidate-work-history-address-0-us-state': COMMON_OPTIONS.US_STATES,
      'workHistory.mayWeContactSupervisor.0': COMMON_OPTIONS.YES_NO,
      
      // Education History fields
      'educationHistory.type.0': COMMON_OPTIONS.SCHOOL_TYPES,
      'educationHistory.didYouGraduate.0': COMMON_OPTIONS.YES_NO,
      'educationHistory.country.0': COMMON_OPTIONS.COUNTRIES,
      'educationHistory.state.0': COMMON_OPTIONS.US_STATES,
    },
    
    fieldConstraints: {
      // Date constraints
      'info.dateAvailableToStart': {
        min: '1920-01-01',
        format: 'MM/DD/YYYY'
      }
    }
  }
  
  // Add more form-specific configs here as needed for other demo forms
];

/**
 * Enhance a field with form-specific options and constraints
 */
export function enhanceField(
  fieldId: string,
  url: string | undefined,
  currentOptions: string[] | undefined,
  currentConstraints: Record<string, string | number | boolean> | undefined
): {
  options: string[] | undefined;
  constraints: Record<string, string | number | boolean> | undefined;
} {
  if (!url) {
    return { options: currentOptions, constraints: currentConstraints };
  }
  
  // Find matching form enhancement config
  const config = FORM_ENHANCEMENTS.find(cfg => url.includes(cfg.urlPattern));
  if (!config) {
    return { options: currentOptions, constraints: currentConstraints };
  }
  
  // Apply field-specific options (only if not already present)
  const options = currentOptions ?? config.fieldOptions?.[fieldId];
  
  // Merge constraints
  const constraints = {
    ...currentConstraints,
    ...config.fieldConstraints?.[fieldId]
  };
  
  return {
    options,
    constraints: Object.keys(constraints).length > 0 ? constraints : undefined
  };
}

/**
 * Check if a URL has form-specific enhancements available
 */
export function hasEnhancements(url: string | undefined): boolean {
  if (!url) return false;
  return FORM_ENHANCEMENTS.some(cfg => url.includes(cfg.urlPattern));
}
