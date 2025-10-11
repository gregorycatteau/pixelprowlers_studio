import { defineNuxtPlugin } from '#app'
import * as Sentry from '@sentry/vue'

export default defineNuxtPlugin((nuxtApp) => {
  const runtimeConfig = nuxtApp.$config
  const dsn = runtimeConfig.public.sentryDsn as string | undefined
  if (!dsn) {
    return
  }

  const router = nuxtApp.$router

  Sentry.init({
    app: nuxtApp.vueApp,
    dsn,
    environment: runtimeConfig.public.sentryEnvironment || runtimeConfig.public.appEnv || 'dev',
    integrations: [
      new Sentry.BrowserTracing({
        routingInstrumentation: router ? Sentry.vueRouterInstrumentation(router) : undefined,
      }),
    ],
    tracesSampleRate: Number(runtimeConfig.public.sentrySampleRate || 0),
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,
    sendDefaultPii: false,
    beforeSend(event) {
      if (event.request?.headers) {
        delete event.request.headers['cookie']
        delete event.request.headers['authorization']
      }
      if (event.request?.cookies) {
        event.request.cookies = {}
      }
      return event
    },
  })
})
