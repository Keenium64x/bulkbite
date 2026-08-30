import frappeUIPreset from "frappe-ui/tailwind"

export default {
  darkMode: ["selector", "[data-theme='dark']", "class"],
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
    "./node_modules/frappe-ui/src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  presets: [frappeUIPreset],
  theme: {
    extend: {
      colors: {
        border: 'var(--theme-border)',
        input: 'var(--theme-border)',
        ring: 'var(--theme-primary)',
        background: 'var(--theme-canvas)',
        foreground: 'var(--theme-text)',
        primary: {
          DEFAULT: 'var(--theme-primary)',
          foreground: 'var(--theme-primary-foreground)'
        },
        secondary: {
          DEFAULT: 'var(--theme-secondary)',
          foreground: 'var(--theme-secondary-foreground)'
        },
        destructive: {
          DEFAULT: 'var(--theme-error)',
          foreground: 'var(--theme-error-foreground)'
        },
        muted: {
          DEFAULT: 'var(--theme-surface)',
          foreground: 'var(--theme-text-muted)'
        },
        accent: {
          DEFAULT: 'var(--theme-accent-soft)',
          foreground: 'var(--theme-text)'
        },
        popover: {
          DEFAULT: 'var(--theme-popup)',
          foreground: 'var(--theme-text)'
        },
        card: {
          DEFAULT: 'var(--theme-surface-raised)',
          foreground: 'var(--theme-text)'
        }
      },
      borderRadius: {
        lg: 'var(--component-radius-card)',
        md: 'var(--component-radius-field)',
        sm: 'var(--component-radius-button)'
      },
      keyframes: {
        'accordion-down': {
          from: {
            height: '0'
          },
          to: {
            height: 'var(--reka-accordion-content-height)'
          }
        },
        'accordion-up': {
          from: {
            height: 'var(--reka-accordion-content-height)'
          },
          to: {
            height: '0'
          }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out'
      }
    }
  },
  plugins: [],
}
