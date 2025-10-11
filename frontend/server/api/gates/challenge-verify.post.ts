import { proxyRequest } from 'h3'
import { djangoBase } from '../../utils/djangoBase'

export default defineEventHandler((event) => {
  const target = new URL('/api/gates/challenge-verify', djangoBase(event)).toString()
  return proxyRequest(event, target)
})
