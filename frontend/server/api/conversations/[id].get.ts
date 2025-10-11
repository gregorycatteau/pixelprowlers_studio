import { createError, proxyRequest } from 'h3'
import { djangoBase } from '../../utils/djangoBase'

export default defineEventHandler((event) => {
  const id = event.context.params?.id
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Conversation id required' })
  }
  const target = new URL(`/api/conversations/${id}/`, djangoBase(event)).toString()
  return proxyRequest(event, target)
})
