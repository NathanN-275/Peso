const appJson = require('./app.json');

const routerBase = process.env.EXPO_PUBLIC_WEB_ROUTER_BASE === '/' ? '/' : '/app';

module.exports = {
  ...appJson.expo,
  experiments: {
    ...appJson.expo.experiments,
    baseUrl: routerBase,
  },
};
