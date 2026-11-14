const { experiments: { baseUrl } } = require('./app.config');

const fontDirectory = baseUrl === '/' ? '/fonts/' : `${baseUrl}/fonts/`;

module.exports = {
  plugins: [
    require('tailwindcss'),
    {
      postcssPlugin: 'peso-font-paths',
      Declaration: {
        src(declaration) {
          if (declaration.parent.name === 'font-face') {
            declaration.value = declaration.value.replace('url("/fonts/', `url("${fontDirectory}`);
          }
        },
      },
    },
  ],
};
