Chapter title: $title

Chapter text:
$body

Reply with a JSON object of this shape:
{
  "scenes": [
    { "summary": "one short sentence describing the shot", "prompt": "english, danbooru, tags, separated, by, commas" }
  ]
}
Return at most $max_scenes scenes.
