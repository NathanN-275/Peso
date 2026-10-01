// Artifact selection never grants access. Netlify keeps candidates private
// until Nathan accepts the complete flow and separately authorizes launch.
export const betaAvailable = process.env.PESO_WEB_BUILD === 'private-beta';
export const betaHref = betaAvailable ? '/app/signup' : '/beta';
export const betaLabel = betaAvailable ? 'Sign up for the beta' : 'Beta coming soon';
