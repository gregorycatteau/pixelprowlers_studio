import { proxyRequest } from 'h3'
import { djangoBase } from '../../utils/djangoBase'

export default defineEventHandler((event) => {
  const target = new URL('/api/gates/absurdity-check', djangoBase(event)).toString()
  return proxyRequest(event, target)
})
