@Controller('cats')
export class CatsController {
  @Get(':id')
  one() {
    return 1
  }
}
