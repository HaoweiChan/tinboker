/**
 * Initialize theme on app load
 * This ensures the theme is applied before the first render
 */
export const initializeTheme = () => {
  try {
    const stored = localStorage.getItem('tinboker-storage');
    if (stored) {
      const { state } = JSON.parse(stored);
      const theme = state?.theme || 'dark';
      
      if (theme === 'dark') {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }
    } else {
      // Default to dark theme
      document.documentElement.classList.add('dark');
    }
  } catch (error) {
    console.error('Failed to initialize theme:', error);
    document.documentElement.classList.add('dark');
  }
};

