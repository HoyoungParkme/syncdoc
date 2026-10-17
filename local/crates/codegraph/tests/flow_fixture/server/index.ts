import express from 'express'
import { PrismaClient } from '@prisma/client'

const prisma = new PrismaClient()
const app = express()

async function show(req, res) {
  const users = await prisma.user.findMany()
  if (!users) throw new Error('없음')
  res.send(users)
}

app.get('/users/:id', show)
app.post('/users', (req, res) => {
  res.send(1)
})
